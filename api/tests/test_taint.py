from shortlist.taint import Taint, decide_amendment


def test_reading_an_application_taints_the_context():
    t = Taint()
    assert not t.tainted
    t.observe("ats", "get_job")
    assert not t.tainted
    t.observe("ats", "get_application")
    assert t.tainted and t.sources == ["ats.get_application"]


def test_agent_amendment_after_untrusted_content_is_refused():
    t = Taint()
    t.mark("caller")
    d = decide_amendment(t, "executor")
    assert not d.accepted
    assert d.label == "REFUSED · untrusted amendment"
    assert "cannot mint permission" in d.reason


def test_agent_can_never_extend_its_own_plan():
    d = decide_amendment(Taint(), "executor")
    assert not d.accepted and d.label == "REFUSED · amendment needs a human"


def test_recruiter_amendment_goes_to_re_signing():
    t = Taint()
    t.mark("ats.get_application")
    assert decide_amendment(t, "recruiter").accepted
