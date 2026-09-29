from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.deps import require_roles
from app.core.roles import Role
from app.models import User
from tests.conftest import BASE_URL, PASSWORD, auth_header

ALL_ROLES = list(Role)


def _officer_payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "email": "new.officer@lm.demo",
        "full_name": "New Officer",
        "role": "LM_OFFICER",
        "password": PASSWORD,
        "state_code": "JH",
        "district_code": "DHN",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize("role", ALL_ROLES)
def test_require_roles_probe(app, make_user, role: Role) -> None:  # noqa: ANN001
    OfficerOnly = Annotated[User, Depends(require_roles(Role.LM_OFFICER))]  # noqa: N806

    @app.get("/api/_probe")
    def probe(user: OfficerOnly) -> dict[str, str]:
        return {"role": user.role.value}

    client = TestClient(app, base_url=BASE_URL)
    res = client.get("/api/_probe", headers=auth_header(make_user(role)))
    if role == Role.LM_OFFICER:
        assert res.status_code == 200
    else:
        assert res.status_code == 403
        assert res.json() == {"detail": "Insufficient permissions"}


def test_require_roles_without_token_is_401(app) -> None:  # noqa: ANN001
    @app.get("/api/_probe")
    def probe(user: Annotated[User, Depends(require_roles(Role.LM_OFFICER))]) -> dict:
        return {}

    assert TestClient(app, base_url=BASE_URL).get("/api/_probe").status_code == 401


@pytest.mark.parametrize("role", ALL_ROLES)
def test_create_user_only_super_admin(client: TestClient, make_user, role: Role) -> None:  # noqa: ANN001
    res = client.post("/api/users", json=_officer_payload(), headers=auth_header(make_user(role)))
    if role == Role.SUPER_ADMIN:
        assert res.status_code == 201
        assert res.json()["role"] == "LM_OFFICER"
        assert res.json()["organization_id"] is None
    else:
        assert res.status_code == 403


def test_created_official_can_log_in(client: TestClient, make_user) -> None:  # noqa: ANN001
    admin = make_user(Role.SUPER_ADMIN)
    client.post("/api/users", json=_officer_payload(), headers=auth_header(admin))
    res = client.post(
        "/api/auth/login", json={"email": "new.officer@lm.demo", "password": PASSWORD}
    )
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "LM_OFFICER"


@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "GATC"},
        {"role": "BUSINESS"},
        {"role": "SUPER_ADMIN"},
        {"state_code": None},
        {"district_code": None},
        {"role": "DISTRICT_ADMIN", "district_code": None},
        {"role": "STATE_ADMIN", "state_code": None, "district_code": None},
        {"role": "STATE_ADMIN", "district_code": "DHN"},
        {"password": "short"},
        {"state_code": "XX"},
        {"state_code": "BR", "district_code": "DHN"},
        {"clearance": "top"},
    ],
)
def test_create_user_validation(client: TestClient, make_user, overrides: dict) -> None:  # noqa: ANN001
    admin = make_user(Role.SUPER_ADMIN)
    body = {k: v for k, v in _officer_payload(**overrides).items() if v is not None}
    assert client.post("/api/users", json=body, headers=auth_header(admin)).status_code == 422


def test_create_state_admin(client: TestClient, make_user) -> None:  # noqa: ANN001
    admin = make_user(Role.SUPER_ADMIN)
    body = _officer_payload(role="STATE_ADMIN", district_code=None)
    body.pop("district_code")
    res = client.post("/api/users", json=body, headers=auth_header(admin))
    assert res.status_code == 201
    assert res.json()["state_code"] == "JH" and res.json()["district_code"] is None


def test_create_user_duplicate_email(client: TestClient, make_user) -> None:  # noqa: ANN001
    admin = make_user(Role.SUPER_ADMIN)
    assert (
        client.post("/api/users", json=_officer_payload(), headers=auth_header(admin)).status_code
        == 201
    )
    res = client.post(
        "/api/users", json=_officer_payload(email="NEW.officer@lm.demo"), headers=auth_header(admin)
    )
    assert res.status_code == 409
