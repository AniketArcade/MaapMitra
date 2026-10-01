"""Spec 17: GET /api/audit-logs. RBAC coverage lives in tests/test_rbac.py."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import PASSWORD, auth_header


def test_system_actor_row_has_null_actor_name(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    client.post("/api/auth/login", json={"email": "nobody@test.demo", "password": "wrong-pass"})

    res = client.get("/api/audit-logs?action=LOGIN_FAILED", headers=auth_header(admin))
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_user_id"] is None
    assert items[0]["actor_name"] is None


def test_actor_name_resolved_for_a_known_actor(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    client.post(
        "/api/users",
        json={
            "email": "resolved.officer@test.demo",
            "full_name": "Resolved Officer",
            "role": "LM_OFFICER",
            "password": PASSWORD,
            "state_code": "JH",
            "district_code": "DHN",
        },
        headers=auth_header(admin),
    )

    res = client.get("/api/audit-logs?action=USER_CREATED", headers=auth_header(admin))
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_user_id"] == str(admin.id)
    assert items[0]["actor_name"] == admin.full_name


def test_filter_by_action(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    client.patch(f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(admin))

    res = client.get("/api/audit-logs?action=USER_STATUS_CHANGED", headers=auth_header(admin))
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["entity_id"] == str(officer.id)


def test_filter_by_actor_user_id(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    client.patch(f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(admin))
    client.patch(f"/api/users/{officer.id}", json={"is_active": True}, headers=auth_header(admin))

    res = client.get(f"/api/audit-logs?actor_user_id={admin.id}", headers=auth_header(admin))
    assert res.json()["total"] >= 2
    assert all(i["actor_user_id"] == str(admin.id) for i in res.json()["items"])


def test_filter_by_entity_type(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    client.patch(f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(admin))

    res = client.get("/api/audit-logs?entity_type=user", headers=auth_header(admin))
    assert res.json()["total"] >= 1
    assert all(i["entity_type"] == "user" for i in res.json()["items"])


def test_date_range_filters_isolate_rows(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    client.patch(f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(admin))

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    future_only = client.get(f"/api/audit-logs?date_from={tomorrow}", headers=auth_header(admin))
    assert future_only.json()["total"] == 0

    today = date.today().isoformat()
    today_inclusive = client.get(
        f"/api/audit-logs?date_from={today}&date_to={today}", headers=auth_header(admin)
    )
    assert today_inclusive.json()["total"] >= 1


def test_pagination(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    for is_active in (False, True, False, True):
        client.patch(
            f"/api/users/{officer.id}", json={"is_active": is_active}, headers=auth_header(admin)
        )

    res = client.get(
        "/api/audit-logs?action=USER_STATUS_CHANGED&page=1&page_size=2",
        headers=auth_header(admin),
    )
    body = res.json()
    assert body["total"] == 4
    assert len(body["items"]) == 2
