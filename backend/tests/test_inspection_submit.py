"""Spec 06: POST /api/inspections/{id}/submit."""

from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import auth_header
from tests.helpers import audit_rows


def _get(client: TestClient, user, inspection_id):  # noqa: ANN001, ANN201
    return client.get(f"/api/inspections/{inspection_id}", headers=auth_header(user)).json()


def _patch(client: TestClient, user, inspection_id, body: dict):  # noqa: ANN001, ANN201
    return client.patch(f"/api/inspections/{inspection_id}", json=body, headers=auth_header(user))


def _submit(client: TestClient, user, inspection_id):  # noqa: ANN001, ANN201
    return client.post(f"/api/inspections/{inspection_id}/submit", headers=auth_header(user))


def test_submit_incomplete_422(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    detail = _get(client, officer, app.inspection.id)
    first_key = detail["checklist_items"][0]["item_key"]
    # Answer everything except one checklist item and every measurement.
    _patch(
        client,
        officer,
        app.inspection.id,
        {
            "checklist_items": [
                {"item_key": i["item_key"], "result": "PASS"} for i in detail["checklist_items"][1:]
            ]
        },
    )
    res = _submit(client, officer, app.inspection.id)
    assert res.status_code == 422
    message = res.json()["detail"][0]["msg"]
    assert first_key in message
    assert "measurements" in message


def test_submit_complete_success(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    detail = _get(client, officer, app.inspection.id)
    _patch(
        client,
        officer,
        app.inspection.id,
        {
            "checklist_items": [
                {"item_key": i["item_key"], "result": "PASS"} for i in detail["checklist_items"]
            ],
            "measurements": [
                {"label": m["label"], "observed_value": "1.000"} for m in detail["measurements"]
            ],
        },
    )
    res = _submit(client, officer, app.inspection.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["submitted_at"] is not None
    assert body["can_edit"] is False

    audits = audit_rows("INSPECTION_SUBMITTED")
    assert len(audits) == 1
    assert audits[0].details["checklist_summary"] == {
        "PASS": len(detail["checklist_items"]),
        "FAIL": 0,
        "NA": 0,
    }

    app_detail = client.get(f"/api/applications/{app.id}", headers=auth_header(officer)).json()
    assert app_detail["status"] == "INSPECTION"  # step 7 decides Approve/Reject, not submit


def test_submit_twice_conflict_no_duplicate_audit(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    detail = _get(client, officer, app.inspection.id)
    _patch(
        client,
        officer,
        app.inspection.id,
        {
            "checklist_items": [
                {"item_key": i["item_key"], "result": "NA"} for i in detail["checklist_items"]
            ],
            "measurements": [
                {"label": m["label"], "observed_value": "0.000"} for m in detail["measurements"]
            ],
        },
    )
    assert _submit(client, officer, app.inspection.id).status_code == 200
    res = _submit(client, officer, app.inspection.id)
    assert (res.status_code, res.json()["detail"]) == (
        409,
        "This inspection has already been submitted",
    )
    assert len(audit_rows("INSPECTION_SUBMITTED")) == 1


def test_submit_wrong_officer_forbidden(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    other_officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _submit(client, other_officer, app.inspection.id)
    assert (res.status_code, res.json()["detail"]) == (403, "Only the assigned officer can do this")
