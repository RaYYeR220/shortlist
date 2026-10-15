import json

from fastapi.testclient import TestClient

from shortlist.app import create_app
from shortlist.llm import ChatReply, ToolCall
from tests.test_runs import Gate


class QuickLLM:
    async def chat(self, **kw):
        if kw.get("json_mode"):
            return ChatReply(json.dumps({"goal": "g", "steps": ["read_application", "note", "decide"]}), [], {})
        return ChatReply(None, [ToolCall("c", "finish", {"summary": "done"}, '{"summary":"done"}')], {})


def test_workspace_creation_is_globally_capped(settings):
    settings.global_workspaces_per_hour = 2
    with TestClient(create_app(settings, gate=Gate(), llm=QuickLLM())) as c:
        assert c.post("/api/workspaces").status_code == 200
        assert c.post("/api/workspaces").status_code == 200
        assert c.post("/api/workspaces").status_code == 429


def test_runs_are_globally_capped_across_workspaces(settings):
    settings.global_runs_per_hour = 2
    with TestClient(create_app(settings, gate=Gate(), llm=QuickLLM())) as c:
        codes = []
        for _ in range(3):
            ws = c.post("/api/workspaces").json()["workspace_id"]
            app_id = c.get(f"/api/workspaces/{ws}").json()["applications"][0]["id"]
            codes.append(c.post("/api/runs", json={"workspace_id": ws, "type": "screen_application", "application_id": app_id}).status_code)
        assert codes == [200, 200, 429]
