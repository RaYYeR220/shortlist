from fastapi.testclient import TestClient

from shortlist.app import create_app

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
HEADERS = {"Authorization": "Bearer test-secret", "Accept": "application/json, text/event-stream"}


def test_mcp_rejects_foreign_host_headers(settings):
    with TestClient(create_app(settings)) as client:
        ok = client.post("/ats/mcp", json=INIT, headers=HEADERS)
        rebound = client.post("/ats/mcp", json=INIT, headers={**HEADERS, "Host": "attacker.example"})
    assert ok.status_code == 200
    assert rebound.status_code >= 400


def test_mcp_accepts_the_public_host(settings):
    settings.public_base_url = "https://shortlist.example"
    with TestClient(create_app(settings), base_url="https://shortlist.example") as client:
        assert client.post("/ats/mcp", json=INIT, headers=HEADERS).status_code == 200


def test_debug_log_is_hidden_without_admin_token(settings):
    settings.admin_token = "adm"
    with TestClient(create_app(settings)) as client:
        assert client.get("/debug/mcp-log").status_code == 404
        assert client.get("/debug/mcp-log", headers={"X-Admin-Token": "nope"}).status_code == 404
        assert client.get("/debug/mcp-log", headers={"X-Admin-Token": "adm"}).status_code == 200
