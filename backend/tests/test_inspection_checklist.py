"""Spec 06: GET/PATCH /api/inspections/{id} - checklist, measurements and overall remarks."""

import pytest
from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import auth_header


def _get(client: TestClient, user, inspection_id):  # noqa: ANN001, ANN201
    return client.get(f"/api/inspections/{inspection_id}", headers=auth_header(user))


def _patch(client: TestClient, user, inspection_id, body: dict):  # noqa: ANN001, ANN201
    return client.patch(f"/api/inspections/{inspection_id}", json=body, headers=auth_header(user))


def test_patch_persists_partial_updates(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    inspection_id = app.inspection.id
    detail = _get(client, officer, inspection_id).json()
    first_key = detail["checklist_items"][0]["item_key"]
    first_label = detail["measurements"][0]["label"]

    res = _patch(
        client,
        officer,
        inspection_id,
        {
            "checklist_items": [{"item_key": first_key, "result": "PASS", "remarks": "looks fine"}],
            "measurements": [{"label": first_label, "observed_value": "12.500"}],
            "overall_remarks": "All good so far",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    item = next(i for i in body["checklist_items"] if i["item_key"] == first_key)
    assert item["result"] == "PASS"
    assert item["remarks"] == "looks fine"
    measurement = next(m for m in body["measurements"] if m["label"] == first_label)
    assert measurement["observed_value"] == pytest.approx(12.5)
    assert body["overall_remarks"] == "All good so far"

    # Other rows are untouched.
    other_items = [i for i in body["checklist_items"] if i["item_key"] != first_key]
    assert all(i["result"] is None for i in other_items)


def test_patch_unknown_checklist_key_422(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _patch(
        client,
        officer,
        app.inspection.id,
        {"checklist_items": [{"item_key": "does_not_exist", "result": "PASS"}]},
    )
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "checklist_items"]


def test_patch_unknown_measurement_label_422(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _patch(
        client,
        officer,
        app.inspection.id,
        {"measurements": [{"label": "999% of capacity", "observed_value": "1.000"}]},
    )
    assert res.status_code == 422


def test_patch_invalid_result_value_422(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    detail = _get(client, officer, app.inspection.id).json()
    first_key = detail["checklist_items"][0]["item_key"]
    res = _patch(
        client,
        officer,
        app.inspection.id,
        {"checklist_items": [{"item_key": first_key, "result": "MAYBE"}]},
    )
    assert res.status_code == 422


def test_patch_wrong_officer_forbidden(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    other_officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _patch(client, other_officer, app.inspection.id, {"overall_remarks": "hijacked"})
    assert (res.status_code, res.json()["detail"]) == (403, "Only the assigned officer can do this")


def test_patch_out_of_jurisdiction_not_found(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    res = _patch(client, outsider, app.inspection.id, {"overall_remarks": "x"})
    assert res.status_code == 404


@pytest.mark.parametrize(
    "role", [Role.BUSINESS, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN, Role.GATC]
)
def test_patch_non_officer_role_rejected(
    client: TestClient, make_user, make_application, role: Role
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _patch(client, make_user(role), app.inspection.id, {"overall_remarks": "x"})
    assert res.status_code == 403


def test_get_visible_to_owning_business(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="INSPECTION", officer=officer)
    res = _get(client, owner, app.inspection.id)
    assert res.status_code == 200
    assert res.json()["can_edit"] is False  # read-only for the business
