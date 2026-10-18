from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.roles import Role
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.models import RefreshToken, User
from tests.conftest import BASE_URL, PASSWORD
from tests.helpers import active_refresh_tokens, audit_rows, set_cookie_headers

MOBILE = {"X-Client": "mobile"}
EMAIL = "biz@test.demo"


def _fresh(client: TestClient) -> TestClient:
    return TestClient(client.app, base_url=BASE_URL)  # no shared cookie jar, like a native app


def _login(client: TestClient, make_user) -> tuple[User, str]:  # noqa: ANN001
    user = make_user(Role.BUSINESS, email=EMAIL)
    res = _fresh(client).post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=MOBILE
    )
    assert res.status_code == 200
    return user, res.json()["refresh_token"]


def _refresh(client: TestClient, raw: str | None, **extra):  # noqa: ANN003, ANN202
    body = {"refresh_token": raw} if raw is not None else None
    return _fresh(client).post("/api/auth/refresh", json=body, headers=MOBILE, **extra)


def _backdate_revocation(raw: str, seconds: int) -> None:
    with SessionLocal() as s:
        s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw))
            .values(revoked_at=datetime.now(UTC) - timedelta(seconds=seconds))
        )
        s.commit()


def test_mobile_login_returns_refresh_token_without_cookies(client, make_user) -> None:  # noqa: ANN001
    user, raw = _login(client, make_user)
    assert raw and len(raw) > 20
    assert active_refresh_tokens(user.id) == 1

    res = _fresh(client).post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=MOBILE
    )
    assert set_cookie_headers(res) == []
    assert res.json()["access_token"]


def test_mobile_header_is_case_insensitive(client, make_user) -> None:  # noqa: ANN001
    make_user(Role.BUSINESS, email=EMAIL)
    res = _fresh(client).post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"x-client": " Mobile "},
    )
    assert res.json()["refresh_token"]
    assert set_cookie_headers(res) == []


def test_mobile_register_returns_refresh_token(client) -> None:  # noqa: ANN001
    res = _fresh(client).post(
        "/api/auth/register",
        headers=MOBILE,
        json={
            "organization_name": "Mobile Traders",
            "state_code": "JH",
            "district_code": "DHN",
            "full_name": "Mobile Owner",
            "email": "mobile.owner@test.demo",
            "password": PASSWORD,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["refresh_token"]
    assert set_cookie_headers(res) == []


def test_web_login_is_unchanged(client, make_user) -> None:  # noqa: ANN001
    make_user(Role.BUSINESS, email=EMAIL)
    res = _fresh(client).post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert res.status_code == 200
    assert res.json()["refresh_token"] is None
    assert res.cookies["lm_refresh"] not in res.text
    cookies = set_cookie_headers(res)
    assert any(c.startswith("lm_refresh=") for c in cookies)
    assert any(c.startswith("lm_session=1") for c in cookies)


def test_mobile_refresh_rotates(client, make_user) -> None:  # noqa: ANN001
    user, old = _login(client, make_user)
    res = _refresh(client, old)
    assert res.status_code == 200
    new = res.json()["refresh_token"]
    assert new and new != old
    assert res.json()["user"]["id"] == str(user.id)
    assert set_cookie_headers(res) == []
    assert active_refresh_tokens(user.id) == 1

    assert _refresh(client, old).status_code == 401  # lost-race window: still rejected
    assert _refresh(client, new).status_code == 200


def test_mobile_reuse_after_grace_revokes_family(client, make_user) -> None:  # noqa: ANN001
    user, old = _login(client, make_user)
    new = _refresh(client, old).json()["refresh_token"]
    _backdate_revocation(old, seconds=11)

    assert _refresh(client, old).status_code == 401
    assert active_refresh_tokens(user.id) == 0
    assert _refresh(client, new).status_code == 401
    rows = audit_rows("REFRESH_REUSE_DETECTED")
    assert len(rows) == 1 and rows[0].actor_user_id == user.id


def test_mobile_refresh_ignores_cookie_and_rejects_missing_or_unknown(
    client,  # noqa: ANN001
    make_user,  # noqa: ANN001
) -> None:
    _, raw = _login(client, make_user)

    cookie_only = _fresh(client).post(
        "/api/auth/refresh", headers={**MOBILE, "Cookie": f"lm_refresh={raw}"}
    )
    assert cookie_only.status_code == 401
    assert _refresh(client, None).status_code == 401
    assert _refresh(client, "not-a-real-token").status_code == 401
    assert _refresh(client, raw).status_code == 200  # the real token was never consumed above


def test_mobile_refresh_body_is_strict(client, make_user) -> None:  # noqa: ANN001
    _, raw = _login(client, make_user)
    extra = _fresh(client).post(
        "/api/auth/refresh", json={"refresh_token": raw, "role": "SUPER_ADMIN"}, headers=MOBILE
    )
    assert extra.status_code == 422
    empty = _fresh(client).post("/api/auth/refresh", json={"refresh_token": ""}, headers=MOBILE)
    assert empty.status_code == 422


def test_web_refresh_ignores_body(client, make_user) -> None:  # noqa: ANN001
    _, mobile_raw = _login(client, make_user)
    res = _fresh(client).post("/api/auth/refresh", json={"refresh_token": mobile_raw})
    assert res.status_code == 401  # no cookie -> web path never reads the body


def test_mobile_logout_revokes_token_and_is_idempotent(client, make_user) -> None:  # noqa: ANN001
    user, raw = _login(client, make_user)
    for _ in range(2):
        res = _fresh(client).post("/api/auth/logout", json={"refresh_token": raw}, headers=MOBILE)
        assert res.status_code == 204
        assert set_cookie_headers(res) == []
    assert active_refresh_tokens(user.id) == 0
    assert len(audit_rows("LOGOUT")) == 1
    assert _refresh(client, raw).status_code == 401


def test_mobile_logout_without_body_is_a_noop(client, make_user) -> None:  # noqa: ANN001
    user, _ = _login(client, make_user)
    res = _fresh(client).post("/api/auth/logout", headers=MOBILE)
    assert res.status_code == 204
    assert active_refresh_tokens(user.id) == 1


def test_mobile_inactive_user_cannot_refresh(client, make_user) -> None:  # noqa: ANN001
    user, raw = _login(client, make_user)
    with SessionLocal() as s:
        s.execute(update(User).where(User.id == user.id).values(is_active=False))
        s.commit()
    assert _refresh(client, raw).status_code == 401
