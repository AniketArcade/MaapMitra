from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import register_body


def test_login_per_email_limit(client: TestClient, make_user) -> None:  # noqa: ANN001
    make_user(Role.BUSINESS, email="biz@test.demo")
    body = {"email": "biz@test.demo", "password": "WrongPass123"}
    for _ in range(5):
        assert client.post("/api/auth/login", json=body).status_code == 401
    assert client.post("/api/auth/login", json=body).status_code == 429
    # a different email from the same IP is still allowed
    other = {"email": "other@test.demo", "password": "WrongPass123"}
    assert client.post("/api/auth/login", json=other).status_code == 401


def test_login_per_ip_limit(client: TestClient) -> None:
    for i in range(20):
        body = {"email": f"user{i}@test.demo", "password": "WrongPass123"}
        assert client.post("/api/auth/login", json=body).status_code == 401
    res = client.post("/api/auth/login", json={"email": "x@test.demo", "password": "WrongPass1"})
    assert res.status_code == 429
    assert res.json() == {"detail": "Too many requests. Try again later."}


def test_register_per_ip_limit(client: TestClient) -> None:
    for i in range(10):
        body = register_body(email=f"owner{i}@test.demo")
        assert client.post("/api/auth/register", json=body).status_code == 201
    res = client.post("/api/auth/register", json=register_body(email="late@test.demo"))
    assert res.status_code == 429
