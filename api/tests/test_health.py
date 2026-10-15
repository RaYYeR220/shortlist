from fastapi.testclient import TestClient

from shortlist.app import create_app


def test_health_reports_ok(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
