"""Spec 20: GATC admitted to GET /applications(/stats), GET /api/certificates, and
GET/POST/DELETE /documents (Reader + Uploader) -- four pure router-gate widenings, zero service
changes, since scope_applications()'s GATC branch (spec 15) already resolves correctly for every
one of them. RBAC-sweep coverage (the flip from 403 to scoped 200/404) lives in test_rbac.py and
test_applications_rbac.py; this file covers the positive case -- an assigned GATC user actually
using the access this spec opens, end to end, built on tests/test_gatc_eligibility.py's own
scheduling-to-GATC fixture shape."""

from fastapi.testclient import TestClient

from app.core import clock
from app.core.roles import Role
from tests.conftest import PDF_BYTES, auth_header, upload
from tests.helpers import submit_checklist

# Category 15 (Taximeter): vehicleRegNo + tariffRef required (tests/test_instrument_categories.py).
CATEGORY_15_VALUES = {"vehicleRegNo": "JH01AB1234", "tariffRef": "Standard tariff card #4"}


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


def _schedule_to_gatc(client: TestClient, officer, gatc, owner, instrument, make_application):  # noqa: ANN001, ANN201
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


def test_gatc_sees_only_assigned_application_in_list(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    app = _schedule_to_gatc(client, officer, gatc, owner, instrument, make_application)

    res = client.get("/api/applications", headers=auth_header(gatc))
    assert res.status_code == 200, res.text
    assert {a["id"] for a in res.json()["items"]} == {app["id"]}

    other_gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    empty = client.get("/api/applications", headers=auth_header(other_gatc))
    assert empty.status_code == 200, empty.text
    assert empty.json()["total"] == 0


def test_gatc_can_read_assigned_application_documents(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    app = _schedule_to_gatc(client, officer, gatc, owner, instrument, make_application)
    doc_id = client.get(f"/api/applications/{app['id']}", headers=auth_header(owner)).json()[
        "documents"
    ][0]["id"]

    res = client.get(f"/api/documents/{doc_id}/url", headers=auth_header(gatc))
    assert res.status_code == 200, res.text

    other_gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    res = client.get(f"/api/documents/{doc_id}/url", headers=auth_header(other_gatc))
    assert res.status_code == 404


def test_gatc_can_view_own_certificate_once_issued(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    app = _schedule_to_gatc(client, officer, gatc, owner, instrument, make_application)
    app_id = app["id"]

    start = client.patch(
        f"/api/applications/{app_id}/status",
        json={"status": "INSPECTION"},
        headers=auth_header(gatc),
    )
    assert start.status_code == 200, start.text
    inspection_id = start.json()["inspection"]["id"]
    submit_checklist(client, gatc, inspection_id)
    approve = client.patch(
        f"/api/applications/{app_id}/status", json={"status": "APPROVED"}, headers=auth_header(gatc)
    )
    assert approve.status_code == 200, approve.text

    # Certificate issuance stays LM_OFFICER-only, untouched by this spec.
    issued = client.post(f"/api/applications/{app_id}/certificate", headers=auth_header(officer))
    assert issued.status_code == 200, issued.text
    cert_id = issued.json()["certificate"]["id"]

    list_res = client.get("/api/certificates", headers=auth_header(gatc))
    assert list_res.status_code == 200, list_res.text
    assert cert_id in {c["id"] for c in list_res.json()["items"]}

    detail_res = client.get(f"/api/certificates/{cert_id}", headers=auth_header(gatc))
    assert detail_res.status_code == 200, detail_res.text

    other_gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    assert (
        client.get(f"/api/certificates/{cert_id}", headers=auth_header(other_gatc)).status_code
        == 404
    )


def test_gatc_can_upload_and_delete_evidence_during_own_inspection(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    app = _schedule_to_gatc(client, officer, gatc, owner, instrument, make_application)
    app_id = app["id"]

    start = client.patch(
        f"/api/applications/{app_id}/status",
        json={"status": "INSPECTION"},
        headers=auth_header(gatc),
    )
    assert start.status_code == 200, start.text

    res = upload(client, gatc, app_id, document_type="INSPECTION_EVIDENCE")
    assert res.status_code == 201, res.text
    doc_id = res.json()["id"]

    delete_res = client.delete(f"/api/documents/{doc_id}", headers=auth_header(gatc))
    assert delete_res.status_code == 204

    # The ordinary-document branch of _check_upload_allowed stays BUSINESS-only -- GATC still
    # cannot touch applicant-submitted document types, even during its own active inspection.
    rejected = upload(client, gatc, app_id, document_type="PROOF_OF_OWNERSHIP", data=PDF_BYTES)
    assert rejected.status_code == 403


def test_gatc_still_forbidden_elsewhere(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    """Proves the four router-gate widenings in spec 20 didn't leak anywhere else."""
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, category_id=15, category_values=CATEGORY_15_VALUES)
    gatc = make_user(Role.GATC, gatc_eligible_category_ids=[15])
    _schedule_to_gatc(client, officer, gatc, owner, instrument, make_application)
    headers = auth_header(gatc)

    assert client.get("/api/instruments", headers=headers).status_code == 403
    assert client.get("/api/admin/certificates/stats", headers=headers).status_code == 403
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.get("/api/audit-logs", headers=headers).status_code == 403
    assert client.get("/api/organizations?type=GATC", headers=headers).status_code == 403
