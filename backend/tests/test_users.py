"""Spec 17: GET /api/users (official-account directory) and PATCH /api/users/{id} (activate/
deactivate). RBAC coverage (403 for every non-SUPER_ADMIN role) lives in tests/test_rbac.py."""

from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import PASSWORD, auth_header
from tests.helpers import audit_rows, submit_checklist


def test_list_excludes_business_and_gatc(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    make_user(Role.BUSINESS)
    make_user(Role.GATC, gatc_eligible_category_ids=[1])
    officer = make_user(Role.LM_OFFICER)

    res = client.get("/api/users", headers=auth_header(admin))
    assert res.status_code == 200, res.text
    ids = {u["id"] for u in res.json()["items"]}
    # admin itself + officer are official roles; BUSINESS/GATC never appear here.
    assert ids == {str(admin.id), str(officer.id)}


def test_filter_by_role(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    make_user(Role.STATE_ADMIN)

    res = client.get("/api/users?role=LM_OFFICER", headers=auth_header(admin))
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert {u["id"] for u in items} == {str(officer.id)}


def test_filter_by_state_district_is_active_and_q(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    jh_dhn = make_user(Role.LM_OFFICER, email="findme-dhanbad@test.demo")
    jh_rnc = make_user(Role.LM_OFFICER, state_code="JH", district_code="RNC")
    inactive = make_user(Role.LM_OFFICER, is_active=False)

    res = client.get("/api/users?district_code=RNC", headers=auth_header(admin))
    assert {u["id"] for u in res.json()["items"]} == {str(jh_rnc.id)}

    res = client.get("/api/users?is_active=false", headers=auth_header(admin))
    assert {u["id"] for u in res.json()["items"]} == {str(inactive.id)}

    res = client.get("/api/users?q=findme-dhanbad", headers=auth_header(admin))
    assert {u["id"] for u in res.json()["items"]} == {str(jh_dhn.id)}


def test_pagination(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    for _ in range(5):
        make_user(Role.LM_OFFICER)

    res = client.get("/api/users?role=LM_OFFICER&page=1&page_size=2", headers=auth_header(admin))
    body = res.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1 and body["page_size"] == 2


def test_lm_officer_filter_populates_case_counts(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)

    # Pending: scheduled but not yet inspected.
    make_application(owner, make_instrument(owner), status="SCHEDULED", officer=officer)
    # Completed: inspected (checklist submitted) then rejected — only a case that reached
    # INSPECTION ever has an Inspection.assigned_officer_id row to count against an officer.
    completed = make_application(
        owner, make_instrument(owner), status="INSPECTION", officer=officer
    )
    submit_checklist(client, officer, completed.inspection.id)
    client.patch(
        f"/api/applications/{completed.id}/status",
        json={"status": "REJECTED", "note": "Failed on-site calibration check"},
        headers=auth_header(officer),
    )

    res = client.get("/api/users?role=LM_OFFICER", headers=auth_header(admin))
    row = next(u for u in res.json()["items"] if u["id"] == str(officer.id))
    assert row["pending_cases"] == 1
    assert row["completed_cases"] == 1


def test_case_counts_null_unless_role_filter_is_lm_officer(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    make_user(Role.LM_OFFICER)

    res = client.get("/api/users", headers=auth_header(admin))
    for row in res.json()["items"]:
        assert row["pending_cases"] is None
        assert row["completed_cases"] is None


def test_patch_toggles_is_active_and_blocks_next_login(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER, email="officer.toggle@test.demo")

    res = client.patch(
        f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(admin)
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False

    login = client.post(
        "/api/auth/login", json={"email": "officer.toggle@test.demo", "password": PASSWORD}
    )
    assert login.status_code == 401

    res = client.patch(
        f"/api/users/{officer.id}", json={"is_active": True}, headers=auth_header(admin)
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is True


def test_patch_self_deactivation_is_409(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    res = client.patch(
        f"/api/users/{admin.id}", json={"is_active": False}, headers=auth_header(admin)
    )
    assert res.status_code == 409


def test_patch_unknown_user_is_404(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    res = client.patch(
        "/api/users/00000000-0000-0000-0000-000000000000",
        json={"is_active": False},
        headers=auth_header(admin),
    )
    assert res.status_code == 404


def test_patch_rejects_extra_fields(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    res = client.patch(
        f"/api/users/{officer.id}",
        json={"is_active": True, "email": "new@test.demo"},
        headers=auth_header(admin),
    )
    assert res.status_code == 422


def test_patch_writes_audit_row(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    client.patch(f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(admin))
    rows = [r for r in audit_rows("USER_STATUS_CHANGED") if r.entity_id == officer.id]
    assert len(rows) == 1
    assert rows[0].details == {"is_active": False, "role": "LM_OFFICER"}
    assert rows[0].actor_user_id == admin.id


# ---------------------------------------------------------------------------
# Spec 18: STATE_ADMIN scoping for GET/POST /api/users and PATCH /api/users/{id}. Router-level
# admission (both SUPER_ADMIN and STATE_ADMIN get past the role gate) lives in test_rbac.py; these
# tests cover the actor-aware narrowing that makes it safe to admit STATE_ADMIN at all.
# ---------------------------------------------------------------------------


def _new_user_payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "email": "new.district.officer@lm.demo",
        "full_name": "New District Officer",
        "role": "LM_OFFICER",
        "password": PASSWORD,
        "state_code": "JH",
        "district_code": "DHN",
    }
    body.update(overrides)
    return body


def test_state_admin_list_scoped_to_own_state(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    jh_officer = make_user(Role.LM_OFFICER)  # JH/DHN by default
    ka_officer = make_user(Role.LM_OFFICER, state_code="KA", district_code="BU")
    peer = make_user(Role.STATE_ADMIN, email="peer@test.demo")
    super_admin = make_user(Role.SUPER_ADMIN)

    res = client.get("/api/users", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    ids = {u["id"] for u in res.json()["items"]}
    assert ids == {str(jh_officer.id)}
    assert str(ka_officer.id) not in ids
    assert str(peer.id) not in ids
    assert str(super_admin.id) not in ids
    assert str(state_admin.id) not in ids  # STATE_ADMIN itself is a peer rank, not visible either


def test_state_admin_list_state_code_mismatch_is_422(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    res = client.get("/api/users?state_code=KA", headers=auth_header(state_admin))
    assert res.status_code == 422, res.text
    assert res.json()["detail"][0]["loc"] == ["body", "state_code"]


def test_state_admin_list_role_filter_rejects_peer_or_above(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)
    for role in ("STATE_ADMIN", "SUPER_ADMIN"):
        res = client.get(f"/api/users?role={role}", headers=auth_header(state_admin))
        assert res.status_code == 403, res.text


def test_state_admin_list_role_filter_admits_lower_ranks(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN
    officer = make_user(Role.LM_OFFICER)  # JH/DHN

    res = client.get("/api/users?role=DISTRICT_ADMIN", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    assert {u["id"] for u in res.json()["items"]} == {str(district_admin.id)}

    res = client.get("/api/users?role=LM_OFFICER", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    assert {u["id"] for u in res.json()["items"]} == {str(officer.id)}


def test_state_admin_create_in_state_lower_rank_succeeds(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    for role in ("DISTRICT_ADMIN", "LM_OFFICER"):
        res = client.post(
            "/api/users",
            json=_new_user_payload(role=role, email=f"{role.lower()}@test.demo"),
            headers=auth_header(state_admin),
        )
        assert res.status_code == 201, res.text
        assert res.json()["role"] == role
        assert res.json()["state_code"] == "JH"


def test_state_admin_create_rejects_state_admin_role(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)
    res = client.post(
        "/api/users",
        json=_new_user_payload(role="STATE_ADMIN", district_code=None),
        headers=auth_header(state_admin),
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"][0]["loc"] == ["body", "role"]


def test_state_admin_create_rejects_cross_state(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    res = client.post(
        "/api/users",
        json=_new_user_payload(state_code="KA", district_code="BU"),
        headers=auth_header(state_admin),
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"][0]["loc"] == ["body", "state_code"]


def test_state_admin_patch_in_state_lower_rank_succeeds(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    officer = make_user(Role.LM_OFFICER)  # JH/DHN
    res = client.patch(
        f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(state_admin)
    )
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False


def test_state_admin_patch_cross_state_is_403(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    officer = make_user(Role.LM_OFFICER, state_code="KA", district_code="BU")
    res = client.patch(
        f"/api/users/{officer.id}", json={"is_active": False}, headers=auth_header(state_admin)
    )
    assert res.status_code == 403, res.text


def test_state_admin_patch_peer_or_above_is_403(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    peer = make_user(Role.STATE_ADMIN, email="peer@test.demo")
    super_admin = make_user(Role.SUPER_ADMIN)
    for target in (peer, super_admin):
        res = client.patch(
            f"/api/users/{target.id}", json={"is_active": False}, headers=auth_header(state_admin)
        )
        assert res.status_code == 403, res.text


def test_state_admin_self_deactivation_still_409(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)
    res = client.patch(
        f"/api/users/{state_admin.id}",
        json={"is_active": False},
        headers=auth_header(state_admin),
    )
    assert res.status_code == 409, res.text
