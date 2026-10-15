from fastapi.testclient import TestClient

from shortlist.app import create_app
from shortlist.voice import VOICE_TOOLS, tool_definitions
from tests.test_runs import Gate
from tests.test_screens import CallerLLM


def test_tool_definitions_cover_every_voice_tool():
    defs = tool_definitions("https://api.test", "s3cret")
    assert {d["name"] for d in defs} == set(VOICE_TOOLS)
    assert all(d["api_schema"]["url"].startswith("https://api.test/api/voice/tools/") for d in defs)
    assert all(d["api_schema"]["request_headers"]["X-Voice-Secret"] == "s3cret" for d in defs)


def test_dynamic_variable_properties_carry_only_the_binding():
    # ElevenLabs rejects a property that sets both dynamic_variable and description.
    for d in tool_definitions("https://api.test", "s3cret"):
        props = d["api_schema"]["request_body_schema"]["properties"]
        for key in ("run_id", "workspace_id"):
            assert props[key] == {"type": "string", "dynamic_variable": key}


def test_webhook_requires_the_secret_and_enforces_the_plan(settings):
    settings.voice_webhook_secret = "s3cret"
    llm = CallerLLM()
    with TestClient(create_app(settings, gate=Gate(), llm=llm)) as c:
        ws = c.post("/api/workspaces").json()["workspace_id"]
        app = c.get(f"/api/workspaces/{ws}").json()["applications"][1]
        llm.ws, llm.app = ws, app["id"]
        run_id = c.post("/api/screens", json={"workspace_id": ws, "application_id": app["id"]}).json()["run_id"]
        body = {"run_id": run_id, "workspace_id": ws, "application_id": app["id"], "stage": "offer"}
        assert c.post("/api/voice/tools/set_stage", json=body).status_code == 401
        r = c.post("/api/voice/tools/set_stage", json=body, headers={"X-Voice-Secret": "s3cret"})
        assert r.status_code == 200
        out = r.json()
        assert out["ok"] is False and out["label"] == "BLOCKED · argument drift" and "say" in out


def test_webhook_without_an_active_screen_fails_closed(settings):
    settings.voice_webhook_secret = "s3cret"
    with TestClient(create_app(settings, gate=Gate()), base_url="http://testserver") as c:
        r = c.post("/api/voice/tools/set_stage", json={"run_id": "nope", "stage": "offer"}, headers={"X-Voice-Secret": "s3cret"})
    assert r.json()["ok"] is False and r.json()["label"] == "FAILED CLOSED"
