from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.roles import OrgType, Role
from app.core.security import create_access_token, decode_access_token
from app.db.session import SessionLocal
from app.models import Organization, User
from tests.conftest import auth_header


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _claims(user: User, **overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(user.id),
        "role": user.role.value,
        "org_id": str(user.organization_id) if user.organization_id else None,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return claims


def test_access_token_claims(make_user) -> None:  # noqa: ANN001
    user = make_user(Role.BUSINESS)
    claims = decode_access_token(create_access_token(user))
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "BUSINESS"
    assert claims["org_id"] == str(user.organization_id)
    assert claims["type"] == "access" and claims["jti"]


def test_official_token_has_null_org(make_user) -> None:  # noqa: ANN001
    assert decode_access_token(create_access_token(make_user(Role.LM_OFFICER)))["org_id"] is None


def test_rejected_tokens(client: TestClient, make_user) -> None:  # noqa: ANN001
    user = make_user(Role.BUSINESS)
    secret = get_settings().JWT_SECRET
    good = create_access_token(user)
    past = datetime.now(UTC) - timedelta(minutes=1)
    bad_tokens = {
        "expired": jwt.encode(_claims(user, exp=past), secret, algorithm="HS256"),
        "wrong_secret": jwt.encode(_claims(user), "x" * 40, algorithm="HS256"),
        "alg_none": jwt.encode(_claims(user), None, algorithm="none"),
        "tampered": good[:-2] + ("AA" if not good.endswith("AA") else "BB"),
        "refresh_type": jwt.encode(_claims(user, type="refresh"), secret, algorithm="HS256"),
        "missing_sub": jwt.encode(
            {k: v for k, v in _claims(user).items() if k != "sub"}, secret, algorithm="HS256"
        ),
        "opaque_refresh_string": "not-a-jwt-just-a-refresh-token",
    }
    for name, token in bad_tokens.items():
        res = client.get("/api/auth/me", headers=_bearer(token))
        assert res.status_code == 401, name
    assert client.get("/api/auth/me", headers=_bearer(good)).status_code == 200


def test_raw_refresh_token_is_not_an_access_token(client: TestClient, make_user) -> None:  # noqa: ANN001
    make_user(Role.BUSINESS, email="biz@test.demo")
    login = client.post(
        "/api/auth/login", json={"email": "biz@test.demo", "password": "Password123!"}
    )
    raw_refresh = login.cookies.get("lm_refresh")
    assert client.get("/api/auth/me", headers=_bearer(raw_refresh)).status_code == 401


def test_stale_role_rejected(client: TestClient, make_user) -> None:  # noqa: ANN001
    user = make_user(Role.BUSINESS)
    headers = auth_header(user)
    with SessionLocal() as s:
        s.get(User, user.id).role = Role.GATC  # still org-bound, so constraints hold
        s.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_stale_org_rejected(client: TestClient, make_user) -> None:  # noqa: ANN001
    user = make_user(Role.BUSINESS)
    headers = auth_header(user)
    with SessionLocal() as s:
        other = Organization(
            type=OrgType.BUSINESS, name="Other", state_code="JH", district_code="DHN"
        )
        s.add(other)
        s.flush()
        s.get(User, user.id).organization_id = other.id
        s.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_deactivated_user_rejected_with_valid_token(client: TestClient, make_user) -> None:  # noqa: ANN001
    user = make_user(Role.LM_OFFICER)
    headers = auth_header(user)
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    with SessionLocal() as s:
        s.get(User, user.id).is_active = False
        s.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
