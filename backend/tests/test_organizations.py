"""Spec 17: GET /api/organizations?type=GATC (the GATC directory). RBAC coverage lives in
tests/test_rbac.py. Reuses spec 15's GATC-scheduling recipe (tests/test_gatc_eligibility.py) to
build real pending/completed cases."""

from fastapi.testclient import TestClient

from app.core import clock
from app.core.roles import Role
from tests.conftest import auth_header
from tests.helpers import submit_checklist

CATEGORY_15_VALUES = {"vehicleRegNo": "JH01AB1234", "tariffRef": "Standard tariff card #4"}


def _check_all_review_items(client: TestClient, officer, application_id) -> None:  # noqa: ANN001
    detail = client.get(f"/api/applications/{application_id}", headers=auth_header(officer)).json()
    client.patch(
        f"/api/applications/{application_id}/review-checklist",
        json={
            "items": [
                {"item_key": i["item_key"], "checked": True} for i in detail["review_checklist"]
            ]
        },
        headers=auth_header(officer),
    )


def _schedule_to_gatc(
    client: TestClient, officer, gatc, owner, instrument, make_application
) -> dict:  # noqa: ANN001
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    res = client.patch(
        f"/api/applications/{app.id}/status",
        json={
            "status": "SCHEDULED",
            "scheduled_date": clock.today().isoformat(),
            "gatc_organization_id": str(gatc.organization_id),
            "gatc_user_id": str(gatc.id),
        },
        headers=auth_header(officer),
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_only_gatc_orgs_returned(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    business = make_user(Role.BUSINESS)

    res = client.get("/api/organizations?type=GATC", headers=auth_header(admin))
    assert res.status_code == 200, res.text
    ids = {o["id"] for o in res.json()["items"]}
    assert ids == {str(gatc.organization_id)}
    assert str(business.organization_id) not in ids


def test_type_param_required_and_restricted(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    assert client.get("/api/organizations", headers=auth_header(admin)).status_code == 422
    assert (
        client.get("/api/organizations?type=BUSINESS", headers=auth_header(admin)).status_code
        == 422
    )


def test_eligible_categories_resolved_to_names(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    res = client.get("/api/organizations?type=GATC", headers=auth_header(admin))
    row = next(o for o in res.json()["items"] if o["id"] == str(gatc.organization_id))
    assert row["eligible_categories"] == ["Taximeter"]


def test_active_reflects_active_gatc_user(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    res = client.get("/api/organizations?type=GATC", headers=auth_header(admin))
    row = next(o for o in res.json()["items"] if o["id"] == str(gatc.organization_id))
    assert row["active"] is True
    assert {u["id"] for u in row["users"]} == {str(gatc.id)}

    client.patch(f"/api/users/{gatc.id}", json={"is_active": False}, headers=auth_header(admin))
    res2 = client.get("/api/organizations?type=GATC", headers=auth_header(admin))
    row2 = next(o for o in res2.json()["items"] if o["id"] == str(gatc.organization_id))
    assert row2["active"] is False
    assert row2["users"][0]["is_active"] is False


def test_is_active_filter(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    active_org = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    inactive_org = make_user(Role.GATC, gatc_eligible_category_ids=[16], is_active=False)

    only_active = client.get(
        "/api/organizations?type=GATC&is_active=true", headers=auth_header(admin)
    ).json()["items"]
    assert {o["id"] for o in only_active} == {str(active_org.organization_id)}

    only_inactive = client.get(
        "/api/organizations?type=GATC&is_active=false", headers=auth_header(admin)
    ).json()["items"]
    assert {o["id"] for o in only_inactive} == {str(inactive_org.organization_id)}


def test_state_district_and_q_filters(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    dhn = make_user(Role.GATC, gatc_eligible_category_ids=[15], org_district="DHN")
    rnc = make_user(Role.GATC, gatc_eligible_category_ids=[15], org_district="RNC")

    res = client.get("/api/organizations?type=GATC&district_code=RNC", headers=auth_header(admin))
    assert {o["id"] for o in res.json()["items"]} == {str(rnc.organization_id)}

    res = client.get(
        f"/api/organizations?type=GATC&q={dhn.organization.name}", headers=auth_header(admin)
    )
    assert {o["id"] for o in res.json()["items"]} == {str(dhn.organization_id)}


def test_state_admin_sees_only_own_state_gatc_orgs(client: TestClient, make_user) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    jh_gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])  # JH/DHN by default
    ka_gatc = make_user(
        Role.GATC, gatc_eligible_category_ids=[15], org_state="KA", org_district="BU"
    )

    res = client.get("/api/organizations?type=GATC", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    ids = {o["id"] for o in res.json()["items"]}
    assert ids == {str(jh_gatc.organization_id)}
    assert str(ka_gatc.organization_id) not in ids


def test_state_admin_cross_state_filter_is_empty_not_rejected(
    client: TestClient, make_user
) -> None:
    """Documents the organizations-vs-users asymmetry (spec 18 §4): scope_organizations() already
    floors every query to the caller's own state, so a mismatched state_code filter just ANDs to
    an empty page here — unlike GET /api/users, which has no such floor and must reject (422)."""
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    make_user(Role.GATC, gatc_eligible_category_ids=[15])  # JH/DHN, would match with no filter

    res = client.get("/api/organizations?type=GATC&state_code=KA", headers=auth_header(state_admin))
    assert res.status_code == 200, res.text
    assert res.json()["items"] == []


def test_district_admin_sees_only_own_district_gatc_orgs(client: TestClient, make_user) -> None:
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN
    dhn_gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])  # JH/DHN by default
    rnc_gatc = make_user(
        Role.GATC, gatc_eligible_category_ids=[15], org_district="RNC"
    )  # same state, other district
    ka_gatc = make_user(
        Role.GATC, gatc_eligible_category_ids=[15], org_state="KA", org_district="BU"
    )

    res = client.get("/api/organizations?type=GATC", headers=auth_header(district_admin))
    assert res.status_code == 200, res.text
    ids = {o["id"] for o in res.json()["items"]}
    assert ids == {str(dhn_gatc.organization_id)}
    assert str(rnc_gatc.organization_id) not in ids
    assert str(ka_gatc.organization_id) not in ids


def test_district_admin_cross_district_filter_is_empty_not_rejected(
    client: TestClient, make_user
) -> None:
    """Spec 21 §4: same organizations-vs-users asymmetry as spec 18's own state-level test —
    scope_organizations() already floors every query to the caller's own district, so a
    mismatched district_code filter just ANDs to an empty page here."""
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN
    make_user(Role.GATC, gatc_eligible_category_ids=[15])  # JH/DHN, would match with no filter

    res = client.get(
        "/api/organizations?type=GATC&district_code=RNC", headers=auth_header(district_admin)
    )
    assert res.status_code == 200, res.text
    assert res.json()["items"] == []


def test_pending_and_completed_case_counts(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    admin = make_user(Role.SUPER_ADMIN)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    # Pending: scheduled to this GATC user, not yet inspected.
    pending_instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    _schedule_to_gatc(client, officer, gatc, owner, pending_instrument, make_application)

    # Completed: scheduled, inspected, then rejected.
    completed_instrument = make_instrument(
        owner, category_id=15, category_values=CATEGORY_15_VALUES
    )
    scheduled = _schedule_to_gatc(
        client, officer, gatc, owner, completed_instrument, make_application
    )
    app_id = scheduled["id"]
    start = client.patch(
        f"/api/applications/{app_id}/status",
        json={"status": "INSPECTION"},
        headers=auth_header(gatc),
    )
    inspection_id = start.json()["inspection"]["id"]
    submit_checklist(client, gatc, inspection_id)
    client.patch(
        f"/api/applications/{app_id}/status",
        json={"status": "REJECTED", "note": "Failed calibration check at the test centre"},
        headers=auth_header(gatc),
    )

    res = client.get("/api/organizations?type=GATC", headers=auth_header(admin))
    row = next(o for o in res.json()["items"] if o["id"] == str(gatc.organization_id))
    assert row["pending_cases"] == 1
    assert row["completed_cases"] == 1
