from fastapi.testclient import TestClient

from app.routers import health as health_router


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["db"] is None
    assert body["version"]


def test_health_db_unreachable(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(health_router, "ping_db", lambda: False)
    res = client.get("/api/health?db=true")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["db"] == "unreachable"


def test_health_db_ok(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(health_router, "ping_db", lambda: True)
    res = client.get("/api/health?db=true")
    assert res.status_code == 200
    assert res.json()["db"] == "ok"


def test_cors_allowed_origin(client: TestClient) -> None:
    res = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_disallowed_origin(client: TestClient) -> None:
    res = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in res.headers
