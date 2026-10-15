from shortlist import domain, seed


def test_seed_creates_jobs_applicants_and_slots(engine):
    ws = seed.create_workspace()
    b = domain.board(ws)
    assert len(b["jobs"]) == 2
    assert len(b["applications"]) == len(seed.APPLICANTS)
    assert all(a["email"].endswith("@example.com") for a in b["applications"])
    assert len(domain.list_slots(ws, b["jobs"][0]["id"])) == 6
    ana = next(a for a in b["applications"] if a["name"] == "Ana Costa")
    assert "{other_id}" not in ana["resume_text"]


def test_reset_restores_a_clean_board(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    domain.set_stage(ws, app["id"], "rejected")
    seed.reset_workspace(ws)
    assert all(a["stage"] == "applied" for a in domain.board(ws)["applications"])
