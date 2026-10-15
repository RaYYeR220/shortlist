from shortlist.armor import InvokeOutcome, SignedPlan, Verdict
from shortlist.pipeline import Pipeline, RunContext
from shortlist.plans import Objective, build_plan, canonical_keys
from shortlist.taint import Taint

ALLOW = InvokeOutcome(Verdict("allow", "executed", "armoriq:proxy"), {"done": True})
BLOCK = InvokeOutcome(Verdict("block", "denied by OPA", "armoriq:proxy"))
HOLD = InvokeOutcome(Verdict("hold", "held for approval", "armoriq:proxy", raw={"delegation_context": {"planId": "plan_1"}}))
ERROR = InvokeOutcome(Verdict("error", "invoke failed: boom", "armoriq:proxy"))
EXPIRED = InvokeOutcome(Verdict("error", "token-expired", "armoriq:sdk"))


class FakeGate:
    def __init__(self, invoke=None, open_hold=None):
        self.invokes = list(invoke or [ALLOW])
        self.open_hold_verdict = open_hold or Verdict("hold", "over band", "armoriq:delegation", delegation_id="del_1")
        self.invoked, self.executed = [], []

    def invoke(self, signed, mcp, action, args, *, resume_delegation_id=None):
        self.invoked.append((mcp, action, args, resume_delegation_id))
        return self.invokes.pop(0) if len(self.invokes) > 1 else self.invokes[0]

    def open_hold(self, signed, mcp, action, args, *, amount, reason):
        return self.open_hold_verdict

    def mark_executed(self, delegation_id, plan_id):
        self.executed.append(delegation_id)


class Events:
    def __init__(self):
        self.items = []

    def emit(self, run_id, kind, payload):
        self.items.append((kind, payload))


class Holds:
    def __init__(self, result="approved"):
        self.result = result

    async def wait(self, run_id, delegation_id, **kw):
        return self.result


def ctx(kind="screen_application", salary=None):
    o = Objective(kind, "ws_1", "app_a", "job_1", salary=salary)

    async def resign():
        return SignedPlan("plan_2", "hash2", "root2", "ref2", 9e9, None, {})

    return RunContext("run_1", "ws_1", build_plan(o, canonical_keys(kind)),
                      SignedPlan("plan_1", "hash", "root", "ref", 9e9, None, {}),
                      lambda ref: {"a@example.com"}, Taint(), resign)


def labels(events):
    return [p["label"] for k, p in events.items if k == "decision"]


GOOD = {"workspace_id": "ws_1", "application_id": "app_a", "stage": "phone_screen"}
OFFER = {"workspace_id": "ws_1", "application_id": "app_a", "salary": 190000}


async def test_allowed_call_runs_through_the_proxy():
    gate, events = FakeGate(), Events()
    out = await Pipeline(gate, events, Holds()).attempt(ctx(), "ats", "set_stage", GOOD)
    assert out.kind == "allowed" and out.label == "ALLOWED"
    assert gate.invoked == [("ats", "set_stage", GOOD, None)]
    assert events.items[0][0] == "attempt"


async def test_reading_the_application_taints_the_run():
    c = ctx()
    await Pipeline(FakeGate(), Events(), Holds()).attempt(c, "ats", "get_application", {"workspace_id": "ws_1", "application_id": "app_a"})
    assert c.taint.tainted


async def test_policy_block_on_an_in_plan_tool():
    gate = FakeGate(invoke=[BLOCK])
    out = await Pipeline(gate, Events(), Holds()).attempt(ctx(), "ats", "set_stage", GOOD)
    assert out.label == "BLOCKED · policy" and out.point == "armoriq:proxy"


async def test_enforcement_error_fails_closed():
    gate = FakeGate(invoke=[ERROR])
    out = await Pipeline(gate, Events(), Holds()).attempt(ctx(), "ats", "set_stage", GOOD)
    assert out.label == "FAILED CLOSED"


async def test_not_in_plan_non_denied_tool_is_blocked_locally_without_invoking():
    gate = FakeGate()
    out = await Pipeline(gate, Events(), Holds()).attempt(ctx(), "ats", "create_offer", OFFER)
    assert out.label == "BLOCKED · not in plan" and out.point == "ours:plan-binding"
    assert gate.invoked == []


async def test_off_plan_denied_tool_is_sent_to_armoriq_and_blocked_there():
    gate = FakeGate(invoke=[BLOCK])
    out = await Pipeline(gate, Events(), Holds()).attempt(ctx(), "ats", "export_candidates",
                                                          {"workspace_id": "ws_1", "destination": "x@collector.example"})
    assert out.label == "BLOCKED · policy" and out.point == "armoriq:proxy"
    assert len(gate.invoked) == 1


async def test_argument_drift_never_invokes_and_explains_itself():
    gate = FakeGate()
    out = await Pipeline(gate, Events(), Holds()).attempt(ctx(), "ats", "set_stage", {**GOOD, "stage": "offer"})
    assert out.label == "BLOCKED · argument drift" and gate.invoked == []
    assert out.drift[0]["param"] == "stage" and out.drift[0]["attempted"] == "offer"
    assert "offer" in out.for_model()


async def test_unparseable_arguments_are_refused():
    gate = FakeGate()
    out = await Pipeline(gate, Events(), Holds()).attempt(ctx(), "ats", "set_stage", {"__unparseable__": "{"})
    assert out.kind == "blocked" and gate.invoked == []


async def test_hold_approved_then_resumes_and_marks_the_delegation():
    gate = FakeGate(invoke=[HOLD, ALLOW])
    out = await Pipeline(gate, Events(), Holds("approved")).attempt(ctx("extend_offer", 190000), "ats", "create_offer", OFFER)
    assert out.label == "HELD → APPROVED" and gate.executed == ["del_1"]
    assert gate.invoked[0][3] is None and gate.invoked[1][3] == "del_1"


async def test_hold_rejected_never_resumes():
    gate = FakeGate(invoke=[HOLD, ALLOW])
    out = await Pipeline(gate, Events(), Holds("rejected")).attempt(ctx("extend_offer", 190000), "ats", "create_offer", OFFER)
    assert out.label == "HELD → REJECTED" and len(gate.invoked) == 1 and gate.executed == []


async def test_existing_approval_resumes_without_waiting():
    gate = FakeGate(invoke=[HOLD, ALLOW],
                    open_hold=Verdict("allow", "approved delegation del_9", "armoriq:delegation", delegation_id="del_9"))
    out = await Pipeline(gate, Events(), Holds("rejected")).attempt(ctx("extend_offer", 190000), "ats", "create_offer", OFFER)
    assert out.label == "HELD → APPROVED" and gate.executed == ["del_9"] and gate.invoked[1][3] == "del_9"


async def test_expired_token_is_resigned_once():
    gate = FakeGate(invoke=[EXPIRED, ALLOW])
    c = ctx()
    out = await Pipeline(gate, Events(), Holds()).attempt(c, "ats", "set_stage", GOOD)
    assert out.kind == "allowed" and c.signed.plan_id == "plan_2" and len(gate.invoked) == 2
