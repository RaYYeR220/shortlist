import pytest

from shortlist import domain, seed
from shortlist.plans import DbResolver, Objective, PlanRejected, build_plan, canonical_keys, match_call


def obj(kind="screen_application", **kw):
    base = dict(type=kind, workspace_id="ws_1", application_id="app_a", job_id="job_1")
    base.update(kw)
    return Objective(**base)


BINDINGS = {"candidate_email": {"a@example.com"}, "open_slot": {"slot_1", "slot_2"}}


def resolve(ref):
    return BINDINGS.get(ref, set())


def screen_plan():
    return build_plan(obj(), canonical_keys("screen_application"), "Screen app_a")


def test_build_plan_rejects_steps_outside_the_template():
    with pytest.raises(PlanRejected):
        build_plan(obj(), ["read_application", "note", "decide", "export_everything"])


def test_build_plan_rejects_duplicates_and_missing_required():
    with pytest.raises(PlanRejected):
        build_plan(obj(), ["read_application", "read_application", "note", "decide"])
    with pytest.raises(PlanRejected):
        build_plan(obj(), ["read_application", "note"])


def test_offer_plan_needs_a_salary():
    with pytest.raises(PlanRejected):
        build_plan(obj("extend_offer"), canonical_keys("extend_offer"))


def test_armoriq_params_carry_only_exact_values():
    doc = screen_plan().to_armoriq()
    decide = next(s for s in doc["steps"] if s["action"] == "set_stage")
    assert decide["params"] == {"workspace_id": "ws_1", "application_id": "app_a"}
    assert decide["constraints"]["stage"] == {"in": ["phone_screen", "rejected"]}


def test_exact_call_matches():
    m = match_call(screen_plan(), "ats", "set_stage", {"workspace_id": "ws_1", "application_id": "app_a", "stage": "rejected"}, resolve)
    assert m.status == "match"


def test_same_tool_other_application_is_drift():
    m = match_call(screen_plan(), "ats", "set_stage", {"workspace_id": "ws_1", "application_id": "app_b", "stage": "phone_screen"}, resolve)
    assert m.status == "drift"
    assert [d.param for d in m.drift] == ["application_id"]


def test_stage_outside_the_declared_set_is_drift():
    m = match_call(screen_plan(), "ats", "set_stage", {"workspace_id": "ws_1", "application_id": "app_a", "stage": "offer"}, resolve)
    assert m.status == "drift" and m.drift[0].attempted == "offer"


def test_email_to_anyone_but_the_candidate_is_drift():
    args = {"workspace_id": "ws_1", "application_id": "app_a", "to": "audit@hr-review.example", "template": "rejection", "body": "x"}
    assert match_call(screen_plan(), "comms", "send_email", args, resolve).status == "drift"
    args["to"] = "A@Example.com"
    assert match_call(screen_plan(), "comms", "send_email", args, resolve).status == "match"


def test_tool_not_declared_is_not_in_plan():
    m = match_call(screen_plan(), "ats", "create_offer", {"workspace_id": "ws_1", "application_id": "app_a", "salary": 1}, resolve)
    assert m.status == "not_in_plan"


def test_unexpected_or_unparseable_arguments_are_drift():
    plan = screen_plan()
    padded = {"workspace_id": "ws_1", "application_id": "app_a", "stage": "rejected", "_approvals": 999}
    assert match_call(plan, "ats", "set_stage", padded, resolve).status == "drift"
    assert match_call(plan, "ats", "set_stage", {"__unparseable__": "{oops"}, resolve).status == "drift"


def test_other_workspace_is_drift():
    m = match_call(screen_plan(), "ats", "get_application", {"workspace_id": "ws_2", "application_id": "app_a"}, resolve)
    assert m.status == "drift"


def test_offer_salary_numeric_string_and_optional_currency():
    plan = build_plan(obj("extend_offer", salary=190000), canonical_keys("extend_offer"))
    base = {"workspace_id": "ws_1", "application_id": "app_a"}
    assert match_call(plan, "ats", "create_offer", {**base, "salary": "190000"}, resolve).status == "match"
    assert match_call(plan, "ats", "create_offer", {**base, "salary": 250000}, resolve).status == "drift"


def test_db_resolver_reads_the_trusted_record(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    r = DbResolver(ws, app["id"], app["job_id"])
    assert r("candidate_email") == {app["email"].lower()}
    assert len(r("open_slot")) == 6
    assert r("nonsense") == set()
