import asyncio
import logging
from datetime import timedelta

import sqlalchemy as sa

from . import db, domain
from .armor import MintRefused
from .executor import SYSTEM_PROMPTS, execute, objective_message
from .pipeline import Pipeline, RunContext
from .planner import declare_plan, describe_objective
from .plans import DbResolver, Objective
from .taint import Taint

log = logging.getLogger(__name__)
TERMINAL = {"run.finished", "run.failed", "run.refused"}


class RateLimited(Exception):
    pass


class EventStore:
    def __init__(self):
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._seq: dict[str, int] = {}

    def _next_seq(self, run_id: str) -> int:
        if run_id not in self._seq:
            with db.engine().begin() as conn:
                current = conn.execute(sa.select(sa.func.max(db.event.c.seq)).where(db.event.c.run_id == run_id)).scalar()
            self._seq[run_id] = current or 0
        self._seq[run_id] += 1
        return self._seq[run_id]

    def emit(self, run_id: str, kind: str, payload: dict) -> None:
        seq, at = self._next_seq(run_id), db.utcnow()
        with db.engine().begin() as conn:
            conn.execute(sa.insert(db.event).values(run_id=run_id, seq=seq, kind=kind, payload=payload, created_at=at))
        item = {"seq": seq, "kind": kind, "payload": payload, "at": at.isoformat()}
        for queue in self._subs.get(run_id, []):
            queue.put_nowait(item)

    def history(self, run_id: str) -> list[dict]:
        with db.engine().begin() as conn:
            rows = conn.execute(sa.select(db.event).where(db.event.c.run_id == run_id).order_by(db.event.c.seq)).mappings().all()
        return [{"seq": r["seq"], "kind": r["kind"], "payload": r["payload"], "at": r["created_at"].isoformat()} for r in rows]

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        if queue in self._subs.get(run_id, []):
            self._subs[run_id].remove(queue)


def _set_run(run_id: str, **values) -> None:
    with db.engine().begin() as conn:
        conn.execute(sa.update(db.run).where(db.run.c.id == run_id).values(updated_at=db.utcnow(), **values))


class ApprovalDesk:
    def __init__(self, gate, events: EventStore, timeout_s: float = 900, poll_s: float = 3.0):
        self.gate, self.events, self.timeout_s, self.poll_s = gate, events, timeout_s, poll_s
        self._futures: dict[str, asyncio.Future] = {}

    def _row(self, approval_id: str) -> dict:
        with db.engine().begin() as conn:
            row = conn.execute(sa.select(db.approval).where(db.approval.c.id == approval_id)).mappings().first()
        if row is None:
            raise KeyError(approval_id)
        return domain._clean(row)

    def _resolve(self, approval_id: str, status: str, by: str) -> None:
        with db.engine().begin() as conn:
            conn.execute(sa.update(db.approval)
                         .where(db.approval.c.id == approval_id, db.approval.c.status == "pending")
                         .values(status=status, decided_by=by, decided_at=db.utcnow()))
        future = self._futures.get(approval_id)
        if future and not future.done():
            future.set_result(status)

    async def wait(self, run_id, delegation_id, *, mcp, action, args, amount, reason):
        with db.engine().begin() as conn:
            ws = conn.execute(sa.select(db.run.c.workspace_id).where(db.run.c.id == run_id)).scalar_one()
        approval_id = db.new_id("apr")
        with db.engine().begin() as conn:
            conn.execute(sa.insert(db.approval).values(
                id=approval_id, workspace_id=ws, run_id=run_id, delegation_id=delegation_id, mcp=mcp, action=action,
                args=args, amount=amount, reason=reason, status="pending", created_at=db.utcnow()))
        _set_run(run_id, status="held")
        self.events.emit(run_id, "approval.pending", {"approval_id": approval_id, "delegation_id": delegation_id,
                                                      "mcp": mcp, "action": action, "args": args, "amount": amount})
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._futures[approval_id] = future
        deadline = loop.time() + self.timeout_s
        try:
            while not future.done() and loop.time() < deadline:
                try:
                    await asyncio.wait_for(asyncio.shield(future), timeout=self.poll_s)
                except (asyncio.TimeoutError, TimeoutError):
                    status = await asyncio.to_thread(self.gate.delegation_status, delegation_id)
                    if status in ("approved", "rejected", "expired"):
                        self._resolve(approval_id, status, "armoriq-console")
            if not future.done():
                self._resolve(approval_id, "expired", "timeout")
            return future.result()
        finally:
            self._futures.pop(approval_id, None)
            _set_run(run_id, status="running")

    async def decide(self, approval_id: str, decision: str, by: str) -> dict:
        row = self._row(approval_id)
        if row["status"] != "pending":
            return row
        # Record the decision with ArmorIQ's delegation API too, best-effort. The human's
        # decision here is the gate; a hiring manager can equally approve the held plan in
        # the ArmorIQ console, which delegation-status polling then resumes.
        try:
            if decision == "approved":
                await asyncio.to_thread(self.gate.approve, row["delegation_id"])
            else:
                await asyncio.to_thread(self.gate.reject, row["delegation_id"], f"rejected by {by}")
        except Exception as exc:
            log.warning("delegation %s could not be recorded in ArmorIQ (%s); the local decision stands", decision, exc)
        waiting = approval_id in self._futures
        self._resolve(approval_id, decision, by)
        if not waiting:
            _set_run(row["run_id"], status="interrupted")
        return self._row(approval_id)

    def list(self, workspace_id: str) -> list[dict]:
        with db.engine().begin() as conn:
            rows = conn.execute(sa.select(db.approval).where(db.approval.c.workspace_id == workspace_id)
                                .order_by(db.approval.c.created_at.desc())).mappings().all()
        return [domain._clean(r) for r in rows]


class RunService:
    def __init__(self, *, gate, llm, settings, catalog, events: EventStore, desk: ApprovalDesk):
        self.gate, self.llm, self.settings, self.catalog = gate, llm, settings, catalog
        self.events, self.desk = events, desk
        self.pipeline = Pipeline(gate, events, desk)
        self._tasks: set[asyncio.Task] = set()
        self._contexts: dict[str, RunContext] = {}
        self._transcripts: dict[str, list[dict]] = {}

    def create(self, workspace_id: str, objective_type: str, application_id: str, salary: int | None, posture: str) -> str:
        since = db.utcnow() - timedelta(hours=1)
        with db.engine().begin() as conn:
            recent = conn.execute(sa.select(sa.func.count()).select_from(db.run)
                                  .where(db.run.c.workspace_id == workspace_id, db.run.c.created_at >= since)).scalar()
        if recent >= self.settings.runs_per_workspace_per_hour:
            raise RateLimited("run limit for this workspace reached; try again later")
        job_id = domain.application_job_id(workspace_id, application_id)
        run_id, now = db.new_id("run"), db.utcnow()
        with db.engine().begin() as conn:
            conn.execute(sa.insert(db.run).values(
                id=run_id, workspace_id=workspace_id, objective_type=objective_type, posture=posture, status="created",
                objective_args={"application_id": application_id, "job_id": job_id, "salary": salary},
                created_at=now, updated_at=now))
        return run_id

    def get(self, run_id: str) -> dict:
        with db.engine().begin() as conn:
            row = conn.execute(sa.select(db.run).where(db.run.c.id == run_id)).mappings().first()
        if row is None:
            raise KeyError(run_id)
        return {**domain._clean(row), "events": self.events.history(run_id)}

    def list(self, workspace_id: str) -> list[dict]:
        with db.engine().begin() as conn:
            rows = conn.execute(sa.select(db.run).where(db.run.c.workspace_id == workspace_id)
                                .order_by(db.run.c.created_at.desc()).limit(50)).mappings().all()
        return [domain._clean(r) for r in rows]

    def context(self, run_id: str) -> RunContext | None:
        return self._contexts.get(run_id)

    def start(self, run_id: str) -> None:
        task = asyncio.create_task(self.run_to_end(run_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    def _objective(row: dict) -> Objective:
        args = row["objective_args"]
        return Objective(row["objective_type"], row["workspace_id"], args["application_id"], args["job_id"], salary=args.get("salary"))

    async def _prepare(self, run_id: str) -> tuple[Objective, RunContext] | None:
        row = self.get(run_id)
        objective = self._objective(row)
        _set_run(run_id, status="planning")
        self.events.emit(run_id, "run.planning", {"objective": objective.type, "posture": row["posture"],
                                                  "application_id": objective.application_id})
        plan, trace = await declare_plan(objective, self.llm, self.settings.planner_model)
        self.events.emit(run_id, "plan.declared", {"plan": plan.to_json(), "planner": trace})
        prompt = describe_objective(objective)
        try:
            signed = await asyncio.to_thread(self.gate.sign, plan.to_armoriq(), prompt=prompt, llm=self.settings.planner_model)
        except MintRefused as exc:
            self.events.emit(run_id, "run.refused", {"label": "BLOCKED · policy", **exc.verdict.to_json()})
            _set_run(run_id, status="refused", plan=plan.to_json(), error=exc.verdict.reason)
            return None
        self.events.emit(run_id, "plan.signed", signed.summary())
        _set_run(run_id, status="running", plan=plan.to_json(), signed=signed.summary())

        async def resign():
            fresh = await asyncio.to_thread(self.gate.sign, plan.to_armoriq(), prompt=prompt, llm=self.settings.planner_model)
            _set_run(run_id, signed=fresh.summary())
            return fresh

        ctx = RunContext(run_id, objective.workspace_id, plan, signed,
                         DbResolver(objective.workspace_id, objective.application_id, objective.job_id), Taint(), resign)
        self._contexts[run_id] = ctx
        return objective, ctx

    async def run_to_end(self, run_id: str) -> None:
        try:
            prepared = await self._prepare(run_id)
            if prepared is None:
                return
            objective, ctx = prepared
            posture = self.get(run_id)["posture"]
            messages = [{"role": "system", "content": SYSTEM_PROMPTS[posture]},
                        {"role": "user", "content": objective_message(objective)}]
            summary = await execute(ctx, llm=self.llm, model=self.settings.executor_model, pipeline=self.pipeline,
                                    events=self.events, catalog=self.catalog, messages=messages)
            _set_run(run_id, status="completed", summary=summary)
            self.events.emit(run_id, "run.finished", {"summary": summary})
        except Exception as exc:
            log.exception("run %s failed", run_id)
            _set_run(run_id, status="failed", error=str(exc))
            self.events.emit(run_id, "run.failed", {"error": str(exc)})
        finally:
            if run_id not in self._transcripts:
                self._contexts.pop(run_id, None)

    async def open_screen(self, workspace_id: str, application_id: str, posture: str) -> str:
        run_id = self.create(workspace_id, "phone_screen", application_id, None, posture)
        prepared = await self._prepare(run_id)
        if prepared is None:
            return run_id
        objective, ctx = prepared
        ctx.taint.mark("caller")
        self._transcripts[run_id] = [{"role": "system", "content": SYSTEM_PROMPTS[f"screen_{posture}"]},
                                     {"role": "user", "content": objective_message(objective)}]
        _set_run(run_id, status="running")
        return run_id

    async def screen_say(self, run_id: str, text: str) -> str:
        ctx, messages = self._contexts.get(run_id), self._transcripts.get(run_id)
        if ctx is None or messages is None:
            raise KeyError(run_id)
        text = text.strip()[:1500]
        self.events.emit(run_id, "caller.message", {"text": text})
        messages.append({"role": "user", "content": f"Caller: {text}"})
        reply = await execute(ctx, llm=self.llm, model=self.settings.executor_model, pipeline=self.pipeline,
                              events=self.events, catalog=self.catalog, messages=messages, max_turns=6)
        self.events.emit(run_id, "screener.message", {"text": reply})
        return reply
