import threading
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.roles import Role
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.models import RefreshToken, User
from tests.conftest import BASE_URL, PASSWORD
from tests.helpers import active_refresh_tokens, audit_rows, cleared


def _login(client: TestClient, make_user) -> tuple[User, str]:  # noqa: ANN001
    user = make_user(Role.BUSINESS, email="biz@test.demo")
    res = client.post("/api/auth/login", json={"email": "biz@test.demo", "password": PASSWORD})
    assert res.status_code == 200
    return user, res.cookies["lm_refresh"]


def _refresh(client: TestClient, raw: str | None):  # noqa: ANN202
    headers = {"Cookie": f"lm_refresh={raw}"} if raw else {}
    fresh = TestClient(client.app, base_url=BASE_URL)  # no shared cookie jar
    return fresh.post("/api/auth/refresh", headers=headers)


def _backdate_revocation(raw: str, seconds: int) -> None:
    with SessionLocal() as s:
        s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw))
            .values(revoked_at=datetime.now(UTC) - timedelta(seconds=seconds))
        )
        s.commit()


def test_refresh_rotates(client: TestClient, make_user) -> None:  # noqa: ANN001
    user, old = _login(client, make_user)
    res = _refresh(client, old)
    assert res.status_code == 200
    new = res.cookies["lm_refresh"]
    assert new and new != old
    assert res.json()["user"]["id"] == str(user.id)
    assert active_refresh_tokens(user.id) == 1

    stale = _refresh(client, old)  # within the grace window: race loser, cookies untouched
    assert stale.status_code == 401
    assert not cleared(stale, "lm_refresh")
    assert _refresh(client, new).status_code == 200


def test_reuse_after_grace_revokes_family(client: TestClient, make_user) -> None:  # noqa: ANN001
    user, old = _login(client, make_user)
    new = _refresh(client, old).cookies["lm_refresh"]
    _backdate_revocation(old, seconds=11)

    res = _refresh(client, old)
    assert res.status_code == 401
    assert cleared(res, "lm_refresh") and cleared(res, "lm_session")
    assert active_refresh_tokens(user.id) == 0
    assert _refresh(client, new).status_code == 401  # the thief's rotation is dead too
    rows = audit_rows("REFRESH_REUSE_DETECTED")
    assert len(rows) == 1 and rows[0].actor_user_id == user.id


def test_concurrent_refresh_race(client: TestClient, make_user) -> None:  # noqa: ANN001
    user, raw = _login(client, make_user)
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def go() -> None:
        barrier.wait()
        statuses.append(_refresh(client, raw).status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [200, 401]
    assert active_refresh_tokens(user.id) == 1  # the family was NOT revoked
    assert audit_rows("REFRESH_REUSE_DETECTED") == []


def test_refresh_without_cookie(client: TestClient) -> None:
    res = _refresh(client, None)
    assert res.status_code == 401
    assert cleared(res, "lm_refresh") and cleared(res, "lm_session")


def test_refresh_unknown_token(client: TestClient) -> None:
    res = _refresh(client, "garbage-token")
    assert res.status_code == 401
    assert cleared(res, "lm_refresh")


def test_refresh_expired_token(client: TestClient, make_user) -> None:  # noqa: ANN001
    _, raw = _login(client, make_user)
    with SessionLocal() as s:
        s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        s.commit()
    assert _refresh(client, raw).status_code == 401


def test_refresh_inactive_user(client: TestClient, make_user) -> None:  # noqa: ANN001
    user, raw = _login(client, make_user)
    with SessionLocal() as s:
        s.get(User, user.id).is_active = False
        s.commit()
    assert _refresh(client, raw).status_code == 401


def test_logout_revokes_and_clears(client: TestClient, make_user) -> None:  # noqa: ANN001
    user, raw = _login(client, make_user)
    fresh = TestClient(client.app, base_url=BASE_URL)
    res = fresh.post("/api/auth/logout", headers={"Cookie": f"lm_refresh={raw}"})
    assert res.status_code == 204
    assert cleared(res, "lm_refresh") and cleared(res, "lm_session")
    assert active_refresh_tokens(user.id) == 0
    assert _refresh(client, raw).status_code == 401


def test_logout_without_cookie_is_204(client: TestClient) -> None:
    fresh = TestClient(client.app, base_url=BASE_URL)
    res = fresh.post("/api/auth/logout")
    assert res.status_code == 204
    assert cleared(res, "lm_refresh")
