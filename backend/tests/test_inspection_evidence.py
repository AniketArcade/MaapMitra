"""Spec 06: evidence-photo upload/delete amendments to the documents pipeline (spec 06 A1/A2/A3)."""

import pytest
from fastapi.testclient import TestClient

from app.core.roles import Role
from app.services import documents as documents_service
from tests.conftest import PNG_BYTES, auth_header, upload


def _upload_evidence(client: TestClient, user, application_id):  # noqa: ANN001, ANN201
    return upload(
        client,
        user,
        application_id,
        document_type="INSPECTION_EVIDENCE",
        data=PNG_BYTES,
        filename="evidence.png",
        content_type="image/png",
    )


def _submit(client: TestClient, user, inspection_id):  # noqa: ANN001, ANN201
    return client.post(f"/api/inspections/{inspection_id}/submit", headers=auth_header(user))


def _fill_checklist(client: TestClient, officer, inspection_id):  # noqa: ANN001
    detail = client.get(f"/api/inspections/{inspection_id}", headers=auth_header(officer)).json()
    client.patch(
        f"/api/inspections/{inspection_id}",
        json={
            "checklist_items": [
                {"item_key": i["item_key"], "result": "PASS"} for i in detail["checklist_items"]
            ],
            "measurements": [
                {"label": m["label"], "observed_value": "1.000"} for m in detail["measurements"]
            ],
        },
        headers=auth_header(officer),
    )


def test_officer_uploads_evidence(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _upload_evidence(client, officer, app.id)
    assert res.status_code == 201, res.text
    assert res.json()["document_type"] == "INSPECTION_EVIDENCE"


def test_business_cannot_upload_evidence(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="INSPECTION", officer=officer)
    res = _upload_evidence(client, owner, app.id)
    assert res.status_code == 403


def test_non_assigned_officer_cannot_upload_evidence(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    other_officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    res = _upload_evidence(client, other_officer, app.id)
    assert res.status_code == 403


def test_evidence_blocked_after_submit(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    _fill_checklist(client, officer, app.inspection.id)
    assert _submit(client, officer, app.inspection.id).status_code == 200
    res = _upload_evidence(client, officer, app.id)
    assert (res.status_code, res.json()["detail"]) == (
        409,
        "This inspection has already been submitted",
    )


def test_evidence_and_business_document_caps_are_independent(
    client: TestClient, make_user, make_application, monkeypatch: pytest.MonkeyPatch
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    # make_application's DRAFT phase already uploads the 2 required business documents, so
    # capping business documents at 2 means that cap is already exhausted by the time the
    # application reaches INSPECTION.
    monkeypatch.setattr(documents_service, "MAX_DOCUMENTS", 2)
    app = make_application(owner, status="INSPECTION", officer=officer)
    monkeypatch.setattr(documents_service, "MAX_EVIDENCE_PHOTOS", 1)
    # Evidence photos are counted separately: the exhausted business-document cap doesn't
    # block the first evidence upload.
    assert _upload_evidence(client, officer, app.id).status_code == 201
    over_cap = _upload_evidence(client, officer, app.id)
    assert over_cap.status_code == 409
    assert "evidence photos" in over_cap.json()["detail"]


def test_evidence_delete_symmetric_with_upload(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    other_officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    doc_id = _upload_evidence(client, officer, app.id).json()["id"]

    assert (
        client.delete(f"/api/documents/{doc_id}", headers=auth_header(other_officer)).status_code
        == 403
    )
    assert (
        client.delete(f"/api/documents/{doc_id}", headers=auth_header(officer)).status_code == 204
    )


def test_evidence_never_listed_as_a_requirement(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    _upload_evidence(client, officer, app.id)
    detail = client.get(f"/api/applications/{app.id}", headers=auth_header(officer)).json()
    assert all(r["document_type"] != "INSPECTION_EVIDENCE" for r in detail["requirements"])
