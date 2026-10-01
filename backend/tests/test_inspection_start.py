"""Spec 06: SCHEDULED -> INSPECTION and the checklist/measurement snapshot it creates."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.inspection_templates import CHECKLIST_TEMPLATES, MEASUREMENT_TEMPLATES
from app.core.roles import Role
from app.db.session import SessionLocal
from app.models.inspection import Inspection
from app.models.inspection_checklist import InspectionChecklistItem, InspectionMeasurement
from tests.conftest import auth_header
from tests.helpers import audit_rows


def _start(client: TestClient, user, application_id):  # noqa: ANN001, ANN201
    return client.patch(
        f"/api/applications/{application_id}/status",
        json={"status": "INSPECTION"},
        headers=auth_header(user),
    )


def _snapshot(application_id):  # noqa: ANN001, ANN201
    with SessionLocal() as s:
        inspection = s.scalar(select(Inspection).where(Inspection.application_id == application_id))
        items = list(
            s.scalars(
                select(InspectionChecklistItem).where(
                    InspectionChecklistItem.inspection_id == inspection.id
                )
            )
        )
        measurements = list(
            s.scalars(
                select(InspectionMeasurement).where(
                    InspectionMeasurement.inspection_id == inspection.id
                )
            )
        )
        return inspection, items, measurements


def test_start_success_creates_snapshot(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    res = _start(client, officer, app.id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "INSPECTION"

    instrument = app.instrument
    inspection, items, measurements = _snapshot(app.id)
    template_items = CHECKLIST_TEMPLATES[instrument.instrument_type]
    fractions = MEASUREMENT_TEMPLATES[instrument.instrument_type]
    assert {i.item_key for i in items} == {t.key for t in template_items}
    assert all(i.result is None and i.remarks is None for i in items)
    assert len(measurements) == len(fractions)
    for fraction in fractions:
        label = f"{int(fraction * 100)}% of capacity"
        row = next(m for m in measurements if m.label == label)
        assert float(row.expected_value) == pytest.approx(float(instrument.capacity) * fraction)
        assert row.unit == instrument.capacity_unit.value
        assert row.observed_value is None

    assert len(audit_rows("INSPECTION_STARTED")) == 1


def test_start_snapshot_survives_template_change(
    client: TestClient, make_user, make_application, monkeypatch: pytest.MonkeyPatch
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    assert _start(client, officer, app.id).status_code == 200
    _, items_before, _ = _snapshot(app.id)
    labels_before = {i.item_key: i.label for i in items_before}

    # Mutate the live template after the fact: already-created rows must not change.
    from app.core.inspection_templates import ChecklistItemDef

    monkeypatch.setitem(
        CHECKLIST_TEMPLATES,
        app.instrument.instrument_type,
        [ChecklistItemDef("bogus", "Bogus item added after start")],
    )
    _, items_after, _ = _snapshot(app.id)
    assert {i.item_key: i.label for i in items_after} == labels_before


def test_start_wrong_officer_forbidden(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    other_officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    res = _start(client, other_officer, app.id)
    assert (res.status_code, res.json()["detail"]) == (403, "Only the assigned officer can do this")


def test_start_out_of_jurisdiction_not_found(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    assert _start(client, outsider, app.id).status_code == 404


@pytest.mark.parametrize(
    "role", [Role.BUSINESS, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN, Role.GATC]
)
def test_start_role_rejected(client: TestClient, make_user, make_application, role: Role) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="SCHEDULED", officer=officer)
    # BUSINESS must be the owning org to reach the role check at all (else scope hides it: 404).
    caller = owner if role == Role.BUSINESS else make_user(role)
    # Spec 20: a fresh GATC caller has no Inspection assigned to them -> 404 (out of scope),
    # unlike every other role here, which is in scope but simply the wrong role -> 403.
    expected = 404 if role == Role.GATC else 403
    assert _start(client, caller, app.id).status_code == expected


def test_start_wrong_status_conflict(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = _start(client, officer, app.id)
    assert (res.status_code, res.json()["detail"]) == (409, "Invalid status change")
