import logging
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Organization, User
from tests.conftest import BASE_URL, PASSWORD, auth_header, register_body
from tests.helpers import audit_rows, set_cookie_headers


def test_register_creates_org_and_user(client: TestClient) -> None:
    res = client.post("/api/auth/register", json=register_body())
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["expires_in"] == 15 * 60
    user = body["user"]
    assert user["role"] == "BUSINESS"
    assert user["organization_name"] == "ABC Traders"
    assert (user["state_code"], user["district_code"]) == ("JH", "DHN")

    cookies = set_cookie_headers(res)
    refresh = next(c for c in cookies if c.startswith("lm_refresh="))
    session = next(c for c in cookies if c.startswith("lm_session=1"))
    for c in (refresh, session):
        assert "HttpOnly" in c and "Secure" in c and "SameSite=lax" in c
    assert "Path=/api/auth" in refresh
    assert "Path=/;" in session or session.endswith("Path=/")

    with SessionLocal() as s:
        org = s.scalar(select(Organization))
        assert org is not None and org.name == "ABC Traders"
        assert s.scalar(select(User)).organization_id == org.id


def test_register_ignores_client_role(client: TestClient) -> None:
    res = client.post("/api/auth/register", json=register_body(role="SUPER_ADMIN"))
    assert res.status_code == 201
    assert res.json()["user"]["role"] == "BUSINESS"


def test_register_lowercases_email_and_uppercases_codes(client: TestClient) -> None:
    res = client.post(
        "/api/auth/register",
        json=register_body(email="Owner@ABC.Demo", state_code="jh", district_code="dhn"),
    )
    assert res.status_code == 201
    user = res.json()["user"]
    assert user["email"] == "owner@abc.demo"
    assert (user["state_code"], user["district_code"]) == ("JH", "DHN")


@pytest.mark.parametrize(
    "overrides",
    [
        {"state_code": None},
        {"district_code": None},
        {"state_code": "J1"},
        {"state_code": "JHK"},
        {"district_code": "D"},
        {"district_code": "DHANB"},
        {"password": "short"},
        {"email": "not-an-email"},
    ],
)
def test_register_validation(client: TestClient, overrides: dict) -> None:
    body = {k: v for k, v in register_body(**overrides).items() if v is not None}
    assert client.post("/api/auth/register", json=body).status_code == 422


def test_register_duplicate_email(client: TestClient) -> None:
    assert client.post("/api/auth/register", json=register_body()).status_code == 201
    res = client.post("/api/auth/register", json=register_body(email="OWNER@abc.demo"))
    assert res.status_code == 409
    assert res.json() == {"detail": "Email already registered"}


def test_register_concurrent_duplicate(app) -> None:  # noqa: ANN001
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def go() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        statuses.append(c.post("/api/auth/register", json=register_body()).status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [201, 409]


def test_login_ok(client: TestClient, make_user) -> None:  # noqa: ANN001
    user = make_user(Role.BUSINESS, email="biz@test.demo")
    res = client.post("/api/auth/login", json={"email": "BIZ@test.demo", "password": PASSWORD})
    assert res.status_code == 200
    assert res.json()["user"]["id"] == str(user.id)
    with SessionLocal() as s:
        assert s.get(User, user.id).last_login_at is not None


@pytest.mark.parametrize("case", ["wrong_password", "unknown_email", "inactive"])
def test_login_failures_share_one_message(client: TestClient, make_user, case: str) -> None:  # noqa: ANN001
    make_user(Role.BUSINESS, email="biz@test.demo", is_active=case != "inactive")
    email = "nobody@test.demo" if case == "unknown_email" else "biz@test.demo"
    password = "WrongPass123" if case == "wrong_password" else PASSWORD
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid email or password"}
    assert not any(c.startswith("lm_refresh=") for c in set_cookie_headers(res))


def test_failed_login_audit_survives_the_error(client: TestClient) -> None:
    client.post("/api/auth/login", json={"email": "ghost@test.demo", "password": "whatever1"})
    rows = audit_rows("LOGIN_FAILED")
    assert len(rows) == 1
    assert rows[0].details["email"] == "ghost@test.demo"
    assert "password" not in rows[0].details
    assert rows[0].actor_user_id is None


def test_me(client: TestClient, make_user) -> None:  # noqa: ANN001
    user = make_user(Role.LM_OFFICER)
    res = client.get("/api/auth/me", headers=auth_header(user))
    assert res.status_code == 200
    assert res.json()["role"] == "LM_OFFICER"
    assert res.json()["district_code"] == "DHN"


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_password_is_argon2id(client: TestClient) -> None:
    client.post("/api/auth/register", json=register_body())
    with SessionLocal() as s:
        assert s.scalar(select(User)).password_hash.startswith("$argon2id$")


def test_no_password_or_token_in_logs_or_responses(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    reg = client.post("/api/auth/register", json=register_body())
    login = client.post("/api/auth/login", json={"email": "owner@abc.demo", "password": PASSWORD})
    refresh_cookie = login.cookies.get("lm_refresh")
    assert refresh_cookie
    for res in (reg, login):
        assert PASSWORD not in res.text
        assert refresh_cookie not in res.text
    assert PASSWORD not in caplog.text
    assert refresh_cookie not in caplog.text
    assert login.json()["access_token"] not in caplog.text
