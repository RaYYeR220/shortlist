import asyncio
import json

import pytest

from shortlist import db, domain, seed
from shortlist.armor import InvokeOutcome, MintRefused, SignedPlan, Verdict
from shortlist.config import Settings
from shortlist.llm import ChatReply, ToolCall
from shortlist.runs import ApprovalDesk, EventStore, RateLimited, RunService


class Tok:
    raw_token, policy_snapshot = {}, []


def call_domain(action, args):
    return getattr(domain, action)(**{("ws" if k == "workspace_id" else k): v for k, v in args.items()})


class Gate:
    def __init__(self, mint_error=None, hold=False):
        self.mint_error, self.hold, self.decided = mint_error, hold, []

    def sign(self, plan_doc, *, prompt, llm):
        if self.mint_error:
            raise MintRefused(Verdict("block", self.mint_error, "armoriq:mint"))
        return SignedPlan("plan_x", "hash", "root", "ref", 9e9, Tok(), plan_doc)

    def invoke(self, signed, mcp, action, args, *, resume_delegation_id=None):
        if self.hold and action == "create_offer" and resume_delegation_id is None and not self.decided:
            return InvokeOutcome(Verdict("hold", "above band", "armoriq:proxy", raw={"delegation_context": {"planId": "plan_x"}}))
        return InvokeOutcome(Verdict("allow", "executed", "armoriq:proxy"), call_domain(action, args))

    def open_hold(self, signed, mcp, action, args, *, amount, reason):
        return Verdict("hold", reason, "armoriq:delegation", delegation_id="del_1")

    def delegation_status(self, delegation_id):
        return "approved" if ("approved", delegation_id) in self.decided else "pending"

    def approve(self, delegation_id):
        self.decided.append(("approved", delegation_id))
        return {}

    def reject(self, delegation_id, reason):
        self.decided.append(("rejected", delegation_id))
        return {}

    def mark_executed(self, delegation_id, plan_id):
        pass


class LLMFor:
    """Planner turn first (JSON mode), then executor turns."""

    def __init__(self, planner_json, turns):
        self.planner_json, self.turns = planner_json, list(turns)

    async def chat(self, **kw):
        if kw.get("json_mode"):
            return ChatReply(self.planner_json, [], {})
        calls = self.turns.pop(0) if self.turns else [("finish", {"summary": "done"})]
        return ChatReply(None, [ToolCall(f"c{i}", n, a, json.dumps(a)) for i, (n, a) in enumerate(calls)], {})


def service(gate, llm, **settings_kw):
    events = EventStore()
    desk = ApprovalDesk(gate, events, timeout_s=5, poll_s=0.05)
    settings = Settings(planner_model="m", executor_model="m", **settings_kw)
    return RunService(gate=gate, llm=llm, settings=settings, catalog=[], events=events, desk=desk), desk


async def test_screen_run_completes(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    scope = {"workspace_id": ws, "application_id": app["id"]}
    llm = LLMFor(json.dumps({"goal": "g", "steps": ["read_application", "note", "decide"]}),
                 [[("ats__get_application", scope)],
                  [("ats__add_note", {**scope, "body": "ok"}), ("ats__set_stage", {**scope, "stage": "phone_screen"})]])
    svc, _ = service(Gate(), llm)
    run_id = svc.create(ws, "screen_application", app["id"], None, "gullible")
    await svc.run_to_end(run_id)
    run = svc.get(run_id)
    assert run["status"] == "completed" and run["signed"]["plan_id"] == "plan_x"
    kinds = [e["kind"] for e in run["events"]]
    assert kinds[:3] == ["run.planning", "plan.declared", "plan.signed"] and kinds[-1] == "run.finished"


async def test_mint_refusal_marks_the_run_refused(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    svc, _ = service(Gate(mint_error="export denied"),
                     LLMFor(json.dumps({"goal": "g", "steps": ["read_application", "note", "decide"]}), []))
    run_id = svc.create(ws, "screen_application", app["id"], None, "gullible")
    await svc.run_to_end(run_id)
    assert svc.get(run_id)["status"] == "refused"


async def test_offer_hold_waits_for_the_desk_then_completes(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    scope = {"workspace_id": ws, "application_id": app["id"]}
    llm = LLMFor(json.dumps({"goal": "g", "steps": ["read_application", "offer", "send_offer"]}),
                 [[("ats__create_offer", {**scope, "salary": 190000})]])
    svc, desk = service(Gate(hold=True), llm)
    run_id = svc.create(ws, "extend_offer", app["id"], 190000, "careful")
    task = asyncio.create_task(svc.run_to_end(run_id))
    for _ in range(200):
        await asyncio.sleep(0.02)
        if desk.list(ws):
            break
    approval = desk.list(ws)[0]
    assert approval["status"] == "pending" and approval["delegation_id"] == "del_1"
    await desk.decide(approval["id"], "approved", "hiring-manager")
    again = await desk.decide(approval["id"], "rejected", "someone-else")
    assert again["status"] == "approved"
    await asyncio.wait_for(task, 5)
    assert domain.snapshot(ws)["offers"] == [{"application_id": app["id"], "salary": 190000}]
    assert svc.get(run_id)["status"] == "completed"


async def test_unknown_approval_raises_key_error(engine):
    desk = ApprovalDesk(Gate(), EventStore(), timeout_s=1, poll_s=0.05)
    with pytest.raises(KeyError):
        await desk.decide("apr_missing", "approved", "x")


async def test_deciding_an_orphaned_approval_marks_the_run_interrupted(engine):
    import sqlalchemy as sa
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    svc, desk = service(Gate(), LLMFor("{}", []))
    run_id = svc.create(ws, "extend_offer", app["id"], 190000, "careful")
    with db.engine().begin() as conn:
        conn.execute(sa.insert(db.approval).values(
            id="apr_orphan", workspace_id=ws, run_id=run_id, delegation_id="del_9", mcp="ats", action="create_offer",
            args={}, amount=190000.0, reason="over band", status="pending", created_at=db.utcnow()))
    row = await desk.decide("apr_orphan", "approved", "hiring-manager")
    assert row["status"] == "approved"
    assert svc.get(run_id)["status"] == "interrupted"


async def test_rate_limit(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    svc, _ = service(Gate(), LLMFor("{}", []), runs_per_workspace_per_hour=1)
    svc.create(ws, "screen_application", app["id"], None, "gullible")
    with pytest.raises(RateLimited):
        svc.create(ws, "screen_application", app["id"], None, "gullible")
