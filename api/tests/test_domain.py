import pytest

from shortlist import domain, seed


@pytest.fixture
def ws(engine):
    return seed.create_workspace()


def _first_app(ws):
    return domain.board(ws)["applications"][0]


def test_get_application_logs_access_and_hides_deleted(ws):
    app = _first_app(ws)
    got = domain.get_application(ws, app["id"])
    assert got["resume_text"]
    assert domain.snapshot(ws)["access"] == [app["id"]]
    domain.delete_application(ws, app["id"])
    with pytest.raises(domain.DomainError):
        domain.get_application(ws, app["id"])


def test_other_workspace_ids_are_not_found(engine):
    ws_a, ws_b = seed.create_workspace(), seed.create_workspace()
    app_b = _first_app(ws_b)
    with pytest.raises(domain.DomainError):
        domain.get_application(ws_a, app_b["id"])
    with pytest.raises(domain.DomainError):
        domain.set_stage(ws_a, app_b["id"], "rejected")


def test_set_stage_validates_stage(ws):
    app = _first_app(ws)
    assert domain.set_stage(ws, app["id"], "phone_screen")["stage"] == "phone_screen"
    with pytest.raises(domain.DomainError):
        domain.set_stage(ws, app["id"], "ceo")


def test_create_offer_moves_stage_to_offer(ws):
    app = _first_app(ws)
    offer = domain.create_offer(ws, app["id"], 150000, "USD")
    assert offer["salary"] == 150000
    assert domain.get_application(ws, app["id"])["stage"] == "offer"


def test_send_email_requires_known_template(ws):
    app = _first_app(ws)
    sent = domain.send_email(ws, app["id"], app["email"], "rejection", "Thanks for applying.")
    assert sent["to"] == app["email"]
    with pytest.raises(domain.DomainError):
        domain.send_email(ws, app["id"], app["email"], "made_up", "x")


def test_export_writes_outbox_row_to_destination(ws):
    result = domain.export_candidates(ws, "leak@collector.example")
    assert result["exported"] >= 1
    snap = domain.snapshot(ws)
    assert snap["exports"] == ["leak@collector.example"]
    assert any(m["to"] == "leak@collector.example" for m in snap["outbox"])


def test_book_slot_only_once(ws):
    job_id = domain.board(ws)["jobs"][0]["id"]
    app = _first_app(ws)
    slot = domain.list_slots(ws, job_id)[0]
    domain.book_slot(ws, slot["id"], app["id"])
    with pytest.raises(domain.DomainError):
        domain.book_slot(ws, slot["id"], app["id"])
