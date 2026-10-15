import base64
import json
from collections import deque

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from shortlist.mcp_gate import McpGate, sanitize


async def echo(request: Request):
    return JSONResponse(json.loads(await request.body()))


def _client(secret="s3cret"):
    inner = Starlette(routes=[Route("/mcp", echo, methods=["POST"])])
    return TestClient(McpGate(inner, secret=secret, name="ats", log=deque(maxlen=10)))


def test_rejects_calls_without_the_secret():
    assert _client().post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401


def test_accepts_bearer_and_armoriq_header():
    body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert _client().post("/mcp", json=body, headers={"Authorization": "Bearer s3cret"}).status_code == 200
    packed = base64.b64encode(json.dumps({"authType": "bearer", "token": "s3cret"}).encode()).decode()
    assert _client().post("/mcp", json=body, headers={"X-Armoriq-MCP-Auth": packed}).status_code == 200


def test_strips_top_level_extras_and_underscored_arguments():
    raw = json.dumps({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call", "_iam_context": {"plan_id": "p1"},
        "params": {"name": "set_stage", "arguments": {"stage": "offer", "_approvals": 999}},
    }).encode()
    clean, extras = sanitize(raw)
    data = json.loads(clean)
    assert "_iam_context" not in data
    assert data["params"]["arguments"] == {"stage": "offer"}
    assert extras["_iam_context"] == {"plan_id": "p1"}
    assert extras["arguments"] == {"_approvals": 999}


def test_sanitize_passes_through_non_json():
    assert sanitize(b"not json") == (b"not json", {})


def test_fails_closed_when_no_secret_is_configured():
    body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert _client(secret="").post("/mcp", json=body, headers={"Authorization": "Bearer "}).status_code == 401
