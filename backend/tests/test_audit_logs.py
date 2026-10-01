"""Spec 17: GET /api/audit-logs. RBAC coverage lives in tests/test_rbac.py."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import PASSWORD, auth_header, register_body


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


# ---------------------------------------------------------------------------
# Spec 18 §4/D4: jurisdiction filter for a STATE_ADMIN actor. Router-level admission lives in
# test_rbac.py; these cover the actual filtering logic.
# ---------------------------------------------------------------------------


def test_state_admin_sees_only_in_state_official_actor_rows(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    jh_officer = make_user(Role.LM_OFFICER, email="jh.officer@test.demo")  # JH/DHN
    ka_officer = make_user(
        Role.LM_OFFICER, email="ka.officer@test.demo", state_code="KA", district_code="BU"
    )
    client.post("/api/auth/login", json={"email": jh_officer.email, "password": PASSWORD})
    client.post("/api/auth/login", json={"email": ka_officer.email, "password": PASSWORD})

    res = client.get("/api/audit-logs?action=LOGIN_SUCCEEDED", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    actor_ids = {i["actor_user_id"] for i in res.json()["items"]}
    assert str(jh_officer.id) in actor_ids
    assert str(ka_officer.id) not in actor_ids


def test_state_admin_sees_org_actor_rows_via_organization_state(
    client: TestClient, make_user
) -> None:
    """A BUSINESS/GATC actor has state_code=NULL on their own users row (officials-only column)
    — their jurisdiction is only reachable via users.organization_id -> organizations.state_code,
    the second half of D4's OR condition."""
    state_admin = make_user(Role.STATE_ADMIN)  # JH

    jh_reg = client.post("/api/auth/register", json=register_body(email="jh.owner@test.demo"))
    assert jh_reg.status_code == 201, jh_reg.text
    jh_owner_id = jh_reg.json()["user"]["id"]

    ka_reg = client.post(
        "/api/auth/register",
        json=register_body(
            email="ka.owner@test.demo",
            organization_name="KA Traders",
            state_code="KA",
            district_code="BU",
        ),
    )
    assert ka_reg.status_code == 201, ka_reg.text
    ka_owner_id = ka_reg.json()["user"]["id"]

    res = client.get("/api/audit-logs?action=USER_REGISTERED", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    actor_ids = {i["actor_user_id"] for i in res.json()["items"]}
    assert jh_owner_id in actor_ids
    assert ka_owner_id not in actor_ids


def test_state_admin_excludes_system_actor_rows(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)
    super_admin = make_user(Role.SUPER_ADMIN)
    client.post("/api/auth/login", json={"email": "nobody@test.demo", "password": "wrong-pass"})

    res = client.get("/api/audit-logs?action=LOGIN_FAILED", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    assert res.json()["items"] == []

    res = client.get("/api/audit-logs?action=LOGIN_FAILED", headers=auth_header(super_admin))
    assert len(res.json()["items"]) == 1


def test_state_admin_jurisdiction_filter_composes_with_action_filter(
    client: TestClient, make_user
) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    jh_officer = make_user(Role.LM_OFFICER)  # JH/DHN
    ka_officer = make_user(Role.LM_OFFICER, state_code="KA", district_code="BU")
    client.patch(
        f"/api/users/{jh_officer.id}", json={"is_active": False}, headers=auth_header(state_admin)
    )
    # A SUPER_ADMIN deactivating the KA officer — this is the row the state_admin must never see.
    make_user(Role.SUPER_ADMIN)

    res = client.get("/api/audit-logs?action=USER_STATUS_CHANGED", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    entity_ids = {i["entity_id"] for i in res.json()["items"]}
    assert str(jh_officer.id) in entity_ids
    assert str(ka_officer.id) not in entity_ids


# ---------------------------------------------------------------------------
# Spec 21 §4: jurisdiction filter for a DISTRICT_ADMIN actor — same two outer joins as STATE_ADMIN
# above, with district_code ANDed onto each side. Router-level admission lives in test_rbac.py.
# ---------------------------------------------------------------------------


def test_district_admin_sees_only_in_district_official_actor_rows(
    client: TestClient, make_user
) -> None:
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN
    dhn_officer = make_user(Role.LM_OFFICER, email="dhn.officer@test.demo")  # JH/DHN
    rnc_officer = make_user(
        Role.LM_OFFICER, email="rnc.officer@test.demo", district_code="RNC"
    )  # same state, other district
    ka_officer = make_user(
        Role.LM_OFFICER, email="ka.officer@test.demo", state_code="KA", district_code="BU"
    )
    client.post("/api/auth/login", json={"email": dhn_officer.email, "password": PASSWORD})
    client.post("/api/auth/login", json={"email": rnc_officer.email, "password": PASSWORD})
    client.post("/api/auth/login", json={"email": ka_officer.email, "password": PASSWORD})

    res = client.get("/api/audit-logs?action=LOGIN_SUCCEEDED", headers=auth_header(district_admin))
    assert res.status_code == 200, res.text
    actor_ids = {i["actor_user_id"] for i in res.json()["items"]}
    assert str(dhn_officer.id) in actor_ids
    assert str(rnc_officer.id) not in actor_ids
    assert str(ka_officer.id) not in actor_ids


def test_district_admin_sees_org_actor_rows_via_organization_district(
    client: TestClient, make_user
) -> None:
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN

    dhn_reg = client.post("/api/auth/register", json=register_body(email="dhn.owner@test.demo"))
    assert dhn_reg.status_code == 201, dhn_reg.text
    dhn_owner_id = dhn_reg.json()["user"]["id"]

    rnc_reg = client.post(
        "/api/auth/register",
        json=register_body(
            email="rnc.owner@test.demo",
            organization_name="Ranchi Traders",
            district_code="RNC",
        ),
    )
    assert rnc_reg.status_code == 201, rnc_reg.text
    rnc_owner_id = rnc_reg.json()["user"]["id"]

    res = client.get("/api/audit-logs?action=USER_REGISTERED", headers=auth_header(district_admin))
    assert res.status_code == 200, res.text
    actor_ids = {i["actor_user_id"] for i in res.json()["items"]}
    assert dhn_owner_id in actor_ids
    assert rnc_owner_id not in actor_ids


def test_district_admin_excludes_system_actor_rows(client: TestClient, make_user) -> None:
    district_admin = make_user(Role.DISTRICT_ADMIN)
    super_admin = make_user(Role.SUPER_ADMIN)
    client.post("/api/auth/login", json={"email": "nobody@test.demo", "password": "wrong-pass"})

    res = client.get("/api/audit-logs?action=LOGIN_FAILED", headers=auth_header(district_admin))
    assert res.status_code == 200, res.text
    assert res.json()["items"] == []

    res = client.get("/api/audit-logs?action=LOGIN_FAILED", headers=auth_header(super_admin))
    assert len(res.json()["items"]) == 1


def test_district_admin_jurisdiction_filter_composes_with_action_filter(
    client: TestClient, make_user
) -> None:
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN
    dhn_officer = make_user(Role.LM_OFFICER)  # JH/DHN
    rnc_officer = make_user(Role.LM_OFFICER, district_code="RNC")  # same state, other district
    super_admin = make_user(Role.SUPER_ADMIN)
    client.patch(
        f"/api/users/{dhn_officer.id}",
        json={"is_active": False},
        headers=auth_header(district_admin),
    )
    # A SUPER_ADMIN deactivating the RNC officer — this is the row the district_admin must never
    # see, even though it's the same state.
    client.patch(
        f"/api/users/{rnc_officer.id}", json={"is_active": False}, headers=auth_header(super_admin)
    )

    res = client.get(
        "/api/audit-logs?action=USER_STATUS_CHANGED", headers=auth_header(district_admin)
    )
    assert res.status_code == 200, res.text
    entity_ids = {i["entity_id"] for i in res.json()["items"]}
    assert str(dhn_officer.id) in entity_ids
    assert str(rnc_officer.id) not in entity_ids
