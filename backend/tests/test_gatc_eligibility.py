"""Spec 15: GATC eligibility + allocation.

Covers: GET /api/gatc/eligible and GET /api/gatc/{organization_id}/users; the extended
DOCUMENT_REVIEW -> SCHEDULED transition (self-assign regression + GATC routing, with its
validation rules); and the assigned GATC user's access to the existing
start/perform/approve-reject machinery via the unmodified inspection endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import clock
from app.core.gatc_types import InspectionAssigneeRole
from app.core.roles import Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.inspection import Inspection
from app.models.user import User
from tests.conftest import PASSWORD, auth_header
from tests.helpers import submit_checklist

# Category 15 (Taximeter): vehicleRegNo + tariffRef required (tests/test_instrument_categories.py).
CATEGORY_15_VALUES = {"vehicleRegNo": "JH01AB1234", "tariffRef": "Standard tariff card #4"}


def _add_gatc_user(organization_id: uuid.UUID, *, is_active: bool = True) -> User:
    """A second GATC-role user in an existing GATC org, for tests that need to distinguish
    "any user of this org" from "this specific user"."""
    with SessionLocal() as s:
        user = User(
            email=f"gatc-{uuid.uuid4().hex[:8]}@test.demo",
            password_hash=hash_password(PASSWORD),
            full_name="Second GATC User",
            role=Role.GATC,
            organization_id=organization_id,
            is_active=is_active,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def _check_all_review_items(client: TestClient, officer, application_id) -> None:  # noqa: ANN001
    detail = client.get(f"/api/applications/{application_id}", headers=auth_header(officer)).json()
    res = client.patch(
        f"/api/applications/{application_id}/review-checklist",
        json={
            "items": [
                {"item_key": i["item_key"], "checked": True} for i in detail["review_checklist"]
            ]
        },
        headers=auth_header(officer),
    )
    assert res.status_code == 200, res.text


def _schedule(client: TestClient, user, application_id, **extra):  # noqa: ANN001, ANN201
    body = {"status": "SCHEDULED", "scheduled_date": clock.today().isoformat()} | extra
    return client.patch(
        f"/api/applications/{application_id}/status", json=body, headers=auth_header(user)
    )


def _status(client: TestClient, user, application_id, status: str, **extra):  # noqa: ANN001, ANN201
    body = {"status": status} | extra
    return client.patch(
        f"/api/applications/{application_id}/status", json=body, headers=auth_header(user)
    )


def _inspection_row(application_id) -> Inspection:  # noqa: ANN001
    with SessionLocal() as s:
        return s.scalars(
            select(Inspection).where(Inspection.application_id == application_id)
        ).one()


# ---------------------------------------------------------------------------
# GET /api/gatc/eligible
# ---------------------------------------------------------------------------


def test_eligible_returns_matching_orgs_in_own_jurisdiction(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)  # JH/DHN by default
    matching = make_user(Role.GATC, gatc_eligible_category_ids=[15, 20])
    wrong_category = make_user(Role.GATC, gatc_eligible_category_ids=[16])
    unconfigured = make_user(Role.GATC)
    other_district = make_user(Role.GATC, gatc_eligible_category_ids=[15], org_district="RNC")

    res = client.get("/api/gatc/eligible?category_id=15", headers=auth_header(officer))
    assert res.status_code == 200, res.text
    ids = {row["id"] for row in res.json()}
    assert ids == {str(matching.organization_id)}
    for excluded in (wrong_category, unconfigured, other_district):
        assert str(excluded.organization_id) not in ids


@pytest.mark.parametrize(
    "role", [Role.BUSINESS, Role.GATC, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN]
)
def test_eligible_lm_officer_only(client: TestClient, make_user, role: Role) -> None:  # noqa: ANN001
    res = client.get("/api/gatc/eligible?category_id=15", headers=auth_header(make_user(role)))
    assert res.status_code == 403


def test_eligible_requires_category_id(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    assert client.get("/api/gatc/eligible", headers=auth_header(officer)).status_code == 422


def test_eligible_anonymous(client: TestClient) -> None:
    assert client.get("/api/gatc/eligible?category_id=15").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/gatc/{organization_id}/users
# ---------------------------------------------------------------------------


def test_org_users_lists_active_gatc_users_only(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    inactive = _add_gatc_user(gatc.organization_id, is_active=False)

    res = client.get(f"/api/gatc/{gatc.organization_id}/users", headers=auth_header(officer))
    assert res.status_code == 200, res.text
    ids = {row["id"] for row in res.json()}
    assert str(gatc.id) in ids
    assert str(inactive.id) not in ids


def test_org_users_not_found_for_non_gatc_org(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    business = make_user(Role.BUSINESS)
    res = client.get(f"/api/gatc/{business.organization_id}/users", headers=auth_header(officer))
    assert res.status_code == 404


def test_org_users_not_found_out_of_jurisdiction(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15], org_district="RNC")
    res = client.get(f"/api/gatc/{gatc.organization_id}/users", headers=auth_header(officer))
    assert res.status_code == 404


def test_org_users_not_found_unknown_id(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    res = client.get(f"/api/gatc/{uuid.uuid4()}/users", headers=auth_header(officer))
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# (a) Regression: self-assign LM_OFFICER unchanged
# ---------------------------------------------------------------------------


def test_schedule_self_assigns_lm_officer_unchanged(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)

    res = _schedule(client, officer, app.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inspection"]["assignee_role"] == "LM_OFFICER"
    assert body["inspection"]["assigned_officer_name"] == officer.full_name

    row = _inspection_row(app.id)
    assert row.assigned_officer_id == officer.id
    assert row.assignee_role == InspectionAssigneeRole.LM_OFFICER


# ---------------------------------------------------------------------------
# (b) Valid eligible GATC org + user, OFFICE_TEST_CENTRE application -> success
# ---------------------------------------------------------------------------


def test_schedule_with_eligible_gatc_succeeds(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inspection"]["assignee_role"] == "GATC"
    assert body["inspection"]["assigned_officer_name"] == gatc.full_name

    row = _inspection_row(app.id)
    assert row.assigned_officer_id == gatc.id
    assert row.assignee_role == InspectionAssigneeRole.GATC


# ---------------------------------------------------------------------------
# (c) GATC org not eligible for the application's category -> rejected
# ---------------------------------------------------------------------------


def test_schedule_gatc_not_eligible_for_category_is_409(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[16])  # a different category

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    assert res.status_code == 409, res.text


# ---------------------------------------------------------------------------
# (d) GATC org for an ON_SITE-mode application -> rejected even if category-eligible
# ---------------------------------------------------------------------------


def test_schedule_gatc_rejected_for_on_site_application(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(
        owner, category_id=15, category_values=CATEGORY_15_VALUES, transportable=False
    )
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    assert res.status_code == 409, res.text


# ---------------------------------------------------------------------------
# (e) GATC org for an application whose instrument has no category_id -> rejected
# ---------------------------------------------------------------------------


def test_schedule_gatc_rejected_without_instrument_category(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)  # old-style, no category_id
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    assert res.status_code == 409, res.text


# ---------------------------------------------------------------------------
# Bad references -> 422 (mirrors "unknown category_id -> 422", spec 16)
# ---------------------------------------------------------------------------


def test_schedule_unknown_gatc_organization_is_422(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(uuid.uuid4()),
        gatc_user_id=str(uuid.uuid4()),
    )
    assert res.status_code == 422


def test_schedule_business_org_as_gatc_organization_is_422(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(owner.organization_id),
        gatc_user_id=str(uuid.uuid4()),
    )
    assert res.status_code == 422


def test_schedule_gatc_org_out_of_jurisdiction_is_422(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15], org_district="RNC")

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    assert res.status_code == 422


def test_schedule_unknown_gatc_user_is_422(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(uuid.uuid4()),
    )
    assert res.status_code == 422


def test_schedule_gatc_user_from_different_org_is_422(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc_a = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    gatc_b = make_user(Role.GATC, gatc_eligible_category_ids=[15])  # a different org's user

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc_a.organization_id),
        gatc_user_id=str(gatc_b.id),
    )
    assert res.status_code == 422


def test_schedule_inactive_gatc_user_is_422(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    inactive = _add_gatc_user(gatc.organization_id, is_active=False)

    res = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(inactive.id),
    )
    assert res.status_code == 422


def test_schedule_gatc_pairing_required(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    res = _schedule(client, officer, app.id, gatc_organization_id=str(uuid.uuid4()))
    assert res.status_code == 422


def test_schedule_gatc_fields_rejected_on_other_targets(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SUBMITTED")
    res = _status(
        client,
        officer,
        app.id,
        "DOCUMENT_REVIEW",
        gatc_organization_id=str(uuid.uuid4()),
        gatc_user_id=str(uuid.uuid4()),
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# (f) The assigned GATC user (and only that user) can start/perform/approve-or-reject
# ---------------------------------------------------------------------------


def test_assigned_gatc_can_start_perform_and_approve(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    sched = _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    assert sched.status_code == 200, sched.text

    other_gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    assert (
        client.get(f"/api/applications/{app.id}", headers=auth_header(other_gatc)).status_code
        == 403
    )
    assert _status(client, other_gatc, app.id, "INSPECTION").status_code == 403

    view = client.get(f"/api/applications/{app.id}", headers=auth_header(gatc))
    assert view.status_code == 200, view.text
    assert view.json()["inspection"]["assignee_role"] == "GATC"

    start = _status(client, gatc, app.id, "INSPECTION")
    assert start.status_code == 200, start.text
    inspection_id = start.json()["inspection"]["id"]

    assert (
        client.get(f"/api/inspections/{inspection_id}", headers=auth_header(other_gatc)).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/inspections/{inspection_id}",
            json={"overall_remarks": "hijacked"},
            headers=auth_header(other_gatc),
        ).status_code
        == 403
    )

    detail = client.get(f"/api/inspections/{inspection_id}", headers=auth_header(gatc))
    assert detail.status_code == 200, detail.text
    assert detail.json()["assignee_role"] == "GATC"
    assert detail.json()["can_edit"] is True

    submit_checklist(client, gatc, inspection_id)

    approve = _status(client, gatc, app.id, "APPROVED")
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "APPROVED"


def test_assigned_gatc_can_reject(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    app = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    _check_all_review_items(client, officer, app.id)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    _schedule(
        client,
        officer,
        app.id,
        gatc_organization_id=str(gatc.organization_id),
        gatc_user_id=str(gatc.id),
    )
    start = _status(client, gatc, app.id, "INSPECTION")
    inspection_id = start.json()["inspection"]["id"]
    submit_checklist(client, gatc, inspection_id)

    reject = _status(client, gatc, app.id, "REJECTED", note="Failed calibration check")
    assert reject.status_code == 200, reject.text
    assert reject.json()["status"] == "REJECTED"
