import httpx
import pytest
from armoriq_sdk.exceptions import (
    IntentMismatchException, MCPInvocationException, PolicyBlockedException, PolicyHoldException, TokenExpiredException,
)

from shortlist.armor import ArmorGate, MintRefused


class Tok:
    def __init__(self):
        self.plan_id, self.plan_hash, self.token_id, self.expires_at = "plan_1", "hash_1", "ref_1", 9e9
        self.raw_token = {"merkle_root": "root_1"}
        self.policy_snapshot = []


class Result:
    result, status = {"ok": True}, "success"


class FakeClient:
    def __init__(self, mint_error=None, invoke_error=None, approved=None):
        self.mint_error, self.invoke_error, self.approved = mint_error, invoke_error, approved
        self.created, self.executed, self.invoked = [], [], []

    def capture_plan(self, llm, prompt, plan):
        return {"plan": plan}

    def get_intent_token(self, cap, validity_seconds):
        if self.mint_error:
            raise self.mint_error
        return Tok()

    def invoke(self, mcp, action, token, params, user_email=None):
        self.invoked.append((mcp, action, dict(params)))
        if self.invoke_error:
            raise self.invoke_error
        return Result()

    def check_approved_delegation(self, email, tool, amount, plan_id):
        return self.approved

    def create_delegation_request(self, params):
        self.created.append(params)
        return type("R", (), {"delegation_id": "del_1"})()

    def get_delegation_status(self, delegation_id):
        return "approved"

    def mark_delegation_executed(self, email, delegation_id, plan_id):
        self.executed.append(delegation_id)


def gate_with(handler=None, **client_kw):
    default = lambda r: httpx.Response(200, json={"status": "approved"})
    transport = httpx.MockTransport(handler or default)
    return ArmorGate(api_key="ak_test_x", backend="https://b.test", proxy="https://p.test", agent_id="agent",
                     user_email="analyst@x.test", approver_email="admin@x.test", mcp_token="s",
                     client=FakeClient(**client_kw), http=httpx.Client(transport=transport))


def signed(g):
    return g.sign({"goal": "g", "steps": []}, prompt="p", llm="m")


def test_sign_reads_merkle_root():
    s = signed(gate_with())
    assert (s.plan_id, s.merkle_root, s.intent_reference) == ("plan_1", "root_1", "ref_1")


def test_mint_denial_becomes_mint_refused():
    g = gate_with(mint_error=PolicyBlockedException("denied", enforcement_action="block", reason="export denied"))
    with pytest.raises(MintRefused) as e:
        signed(g)
    assert e.value.verdict.point == "armoriq:mint" and "export" in e.value.verdict.reason


@pytest.mark.parametrize("error,expected,point", [
    (None, "allow", "armoriq:proxy"),
    (PolicyBlockedException("no", reason="denied by OPA"), "block", "armoriq:proxy"),
    (PolicyHoldException("held"), "hold", "armoriq:proxy"),
    (IntentMismatchException("mismatch"), "block", "armoriq:proxy"),
    (TokenExpiredException("expired"), "error", "armoriq:sdk"),
    (MCPInvocationException("bad"), "error", "armoriq:proxy"),
])
def test_invoke_maps_outcomes(error, expected, point):
    g = gate_with(invoke_error=error)
    out = g.invoke(signed(g), "ats", "set_stage", {"a": 1})
    assert out.verdict.action == expected and out.verdict.point == point


def test_invoke_success_returns_result():
    g = gate_with()
    out = g.invoke(signed(g), "ats", "get_application", {"workspace_id": "w"})
    assert out.verdict.action == "allow" and out.result == {"ok": True}


def test_hold_verdict_exposes_the_delegation_context():
    exc = PolicyHoldException("held")
    exc.delegation_context = {"planId": "plan_1", "domain": "ats"}
    g = gate_with(invoke_error=exc)
    out = g.invoke(signed(g), "ats", "create_offer", {"salary": 190000})
    assert out.verdict.action == "hold"
    assert out.verdict.raw["delegation_context"]["planId"] == "plan_1"


def test_resume_injects_the_delegation_fields_into_proxy_params():
    g = gate_with()
    g.invoke(signed(g), "ats", "create_offer", {"salary": 190000}, resume_delegation_id="del_7")
    sent = g.client.invoked[0][2]
    assert sent["_delegation_id"] == "del_7" and sent["_approvals"] == 999
    assert sent["salary"] == 190000


def test_plain_invoke_sends_no_resume_fields():
    g = gate_with()
    g.invoke(signed(g), "ats", "set_stage", {"stage": "rejected"})
    assert g.client.invoked[0][2] == {"stage": "rejected"}


def test_open_hold_reuses_an_existing_approval():
    g = gate_with(approved=type("A", (), {"delegation_id": "del_old"})())
    v = g.open_hold(signed(g), "ats", "create_offer", {"salary": 190000}, amount=190000.0, reason="over band")
    assert v.action == "allow" and v.delegation_id == "del_old"


def test_open_hold_creates_a_delegation_as_the_analyst():
    g = gate_with()
    v = g.open_hold(signed(g), "ats", "create_offer", {"salary": 190000}, amount=190000.0, reason="over band")
    assert v.action == "hold" and v.delegation_id == "del_1"
    assert g.client.created[0].requester_email == "analyst@x.test"


def test_approve_posts_the_delegation_id_and_approver_email():
    seen = {}

    def handler(request):
        seen["email"] = request.headers.get("x-user-email")
        seen["body"] = request.content
        return httpx.Response(200, json={"status": "approved"})

    g = gate_with(handler)
    g.approve("del_1")
    assert seen["email"] == "admin@x.test"
    assert b"del_1" in seen["body"] and b"admin@x.test" in seen["body"]
