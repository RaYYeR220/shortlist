import json

from shortlist import domain, seed
from shortlist.armor import InvokeOutcome, SignedPlan, Verdict
from shortlist.executor import execute
from shortlist.llm import ChatReply, ToolCall
from shortlist.pipeline import Pipeline, RunContext
from shortlist.plans import DbResolver, Objective, build_plan
from shortlist.taint import Taint


def call_domain(action, args):
    return getattr(domain, action)(**{("ws" if k == "workspace_id" else k): v for k, v in args.items()})


class DomainGate:
    """Allows everything at the ArmorIQ layer and executes on the domain, isolating
    plan binding and the executor loop."""

    def invoke(self, signed, mcp, action, args, *, resume_delegation_id=None):
        return InvokeOutcome(Verdict("allow", "executed", "armoriq:proxy"), call_domain(action, args))

    def open_hold(self, *a, **k):
        raise AssertionError("no holds in this test")

    def mark_executed(self, *a):
        pass


class Events:
    def __init__(self):
        self.items = []

    def emit(self, run_id, kind, payload):
        self.items.append((kind, payload))


class Scripted:
    def __init__(self, turns):
        self.turns = list(turns)

    async def chat(self, **kw):
        calls = self.turns.pop(0)
        return ChatReply(None, [ToolCall(f"c{i}", n, a, json.dumps(a)) for i, (n, a) in enumerate(calls)], {})


def context(ws, app, keys, taint=None):
    o = Objective("screen_application", ws, app["id"], app["job_id"])
    return RunContext("run_1", ws, build_plan(o, keys), SignedPlan("p", "h", "r", "ref", 9e9, None, {}),
                      DbResolver(ws, app["id"], app["job_id"]), taint or Taint(), None)


async def test_injected_call_is_refused_and_legit_work_finishes(engine):
    ws = seed.create_workspace()
    apps = domain.board(ws)["applications"]
    dmitri, other = apps[3], apps[0]
    ctx = context(ws, dmitri, ["read_application", "note", "decide"])
    scope = {"workspace_id": ws, "application_id": dmitri["id"]}
    llm = Scripted([
        [("ats__get_application", scope)],
        [("ats__set_stage", {**scope, "stage": "offer"}),
         ("ats__set_stage", {"workspace_id": ws, "application_id": other["id"], "stage": "rejected"})],
        [("ats__add_note", {**scope, "body": "Strong systems background."}), ("ats__set_stage", {**scope, "stage": "phone_screen"})],
        [("finish", {"summary": "Screened."})],
    ])
    events = Events()
    summary = await execute(ctx, llm=llm, model="m", pipeline=Pipeline(DomainGate(), events, None), events=events,
                            catalog=[], messages=[{"role": "user", "content": "go"}])
    snap = domain.snapshot(ws)
    assert summary == "Screened."
    assert snap["stages"][dmitri["id"]] == "phone_screen"
    assert snap["stages"][other["id"]] == "applied"
    labels = [p["label"] for k, p in events.items if k == "decision"]
    assert labels.count("BLOCKED · argument drift") == 2 and labels.count("ALLOWED") == 3


async def test_agent_amendment_is_refused(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    ctx = context(ws, app, ["read_application", "note", "decide"], Taint(["ats.get_application"]))
    llm = Scripted([[("request_amendment", {"mcp": "comms", "action": "send_bulk", "reason": "audit"})], [("finish", {"summary": "done"})]])
    events = Events()
    await execute(ctx, llm=llm, model="m", pipeline=Pipeline(DomainGate(), events, None), events=events, catalog=[],
                  messages=[{"role": "user", "content": "go"}])
    assert any(k == "amendment.decided" and p["label"] == "REFUSED · untrusted amendment" for k, p in events.items)


async def test_identical_refused_call_is_not_resent(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    ctx = context(ws, app, ["read_application", "note", "decide"])
    bad = ("ats__set_stage", {"workspace_id": ws, "application_id": app["id"], "stage": "offer"})
    llm = Scripted([[bad], [bad], [("finish", {"summary": "x"})]])
    events = Events()
    await execute(ctx, llm=llm, model="m", pipeline=Pipeline(DomainGate(), events, None), events=events, catalog=[],
                  messages=[{"role": "user", "content": "go"}])
    kinds = [k for k, _ in events.items]
    assert kinds.count("attempt") == 1 and kinds.count("attempt.suppressed") == 1
