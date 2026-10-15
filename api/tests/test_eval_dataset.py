from shortlist.eval.dataset import CASES, answer_key


def test_thirty_cases_with_the_preregistered_mix():
    assert len(CASES) == 30
    families = [c.family for c in CASES]
    assert families.count("clean") == 18
    for family in ("stage_escalation", "egress", "cross_read", "off_plan_tool", "amendment", "offer_manipulation"):
        assert families.count(family) == 2
    assert all(c.email.endswith(".example") or c.email.endswith("@example.com") for c in CASES)


def test_answer_key_is_stable():
    assert answer_key() == answer_key()
    assert set(answer_key()) == {c.case_id for c in CASES}
