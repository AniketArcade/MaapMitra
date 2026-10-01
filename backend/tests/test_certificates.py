"""Spec 08: certificate issuance (POST /api/applications/{id}/certificate) and reads
(GET /api/certificates/{id}, GET /api/certificates/{id}/pdf)."""

import hashlib
import re
import threading

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Certificate
from tests.conftest import BASE_URL, auth_header
from tests.helpers import audit_rows

CERT_NUMBER_RE = re.compile(r"^LM-CERT-\d{4}-\d{6}$")


def _issue(client: TestClient, user, application_id):  # noqa: ANN001, ANN201
    return client.post(f"/api/applications/{application_id}/certificate", headers=auth_header(user))


def _recompute_hash(app_detail: dict, cert: dict) -> str:
    instrument = app_detail["instrument"]
    payload = "|".join(
        [
            cert["certificate_number"],
            instrument["instrument_uid"],
            instrument["manufacturer"],
            instrument["model"],
            instrument["serial_number"],
            cert["organization_name"],
            cert["valid_from"],
            cert["valid_until"],
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def test_issue_certificate_success(
    client: TestClient, make_user, make_application, storage
) -> None:  # noqa: ANN001
    assigned = make_user(Role.LM_OFFICER)
    other_officer = make_user(Role.LM_OFFICER)  # in-scope, not the one who approved
    app = make_application(status="APPROVED", officer=assigned)

    res = _issue(client, other_officer, app.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "CERTIFICATE_ISSUED"
    cert = body["certificate"]
    assert cert is not None
    assert CERT_NUMBER_RE.match(cert["certificate_number"])
    assert cert["qr_code_data_uri"].startswith("data:image/png;base64,")

    full = client.get(f"/api/certificates/{cert['id']}", headers=auth_header(other_officer)).json()
    audit_detail = next(
        r for r in audit_rows("CERTIFICATE_ISSUED") if str(r.entity_id) == cert["id"]
    ).details
    assert audit_detail["data_hash"] == _recompute_hash(body, full)

    audits = audit_rows("APPLICATION_STATUS_CHANGED")
    changed = [r for r in audits if r.details["to"] == "CERTIFICATE_ISSUED"]
    assert len(changed) == 1

    issued = audit_rows("CERTIFICATE_ISSUED")
    assert len(issued) == 1
    assert issued[0].details["certificate_number"] == cert["certificate_number"]

    # PDF was actually rendered and stored under the documented path shape.
    ((path, (data, content_type)),) = (
        (p, o) for p, o in storage.objects.items() if p.startswith("certificates/")
    )
    assert path == f"certificates/{cert['id']}.pdf"
    assert content_type == "application/pdf"
    assert data.startswith(b"%PDF")

    # The instrument unlocks (CERTIFICATE_ISSUED is terminal).
    instrument = client.get(
        f"/api/instruments/{app.instrument.id}", headers=auth_header(other_officer)
    ).json()
    assert instrument["locked_fields"] == []


def test_issue_certificate_wrong_status(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    # DRAFT is never visible to officials at all (scope_applications), so it 404s, not 409.
    draft = make_application(status="DRAFT")
    assert _issue(client, officer, draft.id).status_code == 404

    for status in ("SUBMITTED", "DOCUMENT_REVIEW", "SCHEDULED", "INSPECTION", "REJECTED"):
        app = make_application(status=status, officer=officer)
        res = _issue(client, officer, app.id)
        assert (res.status_code, res.json()["detail"]) == (
            409,
            "Application must be approved before a certificate can be issued",
        )
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Certificate)) == 0


def test_issue_certificate_role_and_scope(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    app = make_application(owner, status="APPROVED", officer=officer)

    # The route is LM_OFFICER-only (require_roles), enforced before scope is ever checked —
    # every other role gets a uniform 403, in or out of scope, same as every other
    # single-role-gated endpoint in this codebase (e.g. reschedule_inspection).
    assert _issue(client, owner, app.id).status_code == 403
    assert _issue(client, make_user(Role.DISTRICT_ADMIN), app.id).status_code == 403
    assert _issue(client, make_user(Role.SUPER_ADMIN), app.id).status_code == 403
    assert _issue(client, make_user(Role.GATC), app.id).status_code == 403

    # An in-role but out-of-jurisdiction officer reaches the service's own scope check -> 404.
    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    assert _issue(client, outsider, app.id).status_code == 404


def test_issue_certificate_double_issue_race(app, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    approved = make_application(status="APPROVED", officer=officer)
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def go() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        statuses.append(_issue(c, officer, approved.id).status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [200, 409]

    with SessionLocal() as s:
        n = s.scalar(
            select(func.count())
            .select_from(Certificate)
            .where(Certificate.application_id == approved.id)
        )
    assert n == 1


def test_get_certificate_and_pdf_scope(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    admin = make_user(Role.SUPER_ADMIN)
    app = make_application(owner, status="APPROVED", officer=officer)
    cert_id = _issue(client, officer, app.id).json()["certificate"]["id"]

    for reader in (owner, officer, admin):
        assert (
            client.get(f"/api/certificates/{cert_id}", headers=auth_header(reader)).status_code
            == 200
        )
        res = client.get(f"/api/certificates/{cert_id}/pdf", headers=auth_header(reader))
        assert res.status_code == 200
        body = res.json()
        assert body["url"].startswith("https://")
        assert body["expires_in"] <= 300

    attachment_url = client.get(
        f"/api/certificates/{cert_id}/pdf?disposition=attachment", headers=auth_header(owner)
    ).json()["url"]
    assert "download=" in attachment_url

    other_business = make_user(Role.BUSINESS)
    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    assert (
        client.get(f"/api/certificates/{cert_id}", headers=auth_header(other_business)).status_code
        == 404
    )
    assert (
        client.get(f"/api/certificates/{cert_id}", headers=auth_header(outsider)).status_code == 404
    )
    assert (
        client.get(
            f"/api/certificates/{cert_id}/pdf", headers=auth_header(other_business)
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Spec 17 §1.6: GET /api/certificates (list) — no list endpoint existed before this step.
# RBAC (GATC excluded, every other reader admitted) is covered by test_rbac.py.
# ---------------------------------------------------------------------------


def test_list_certificates_pagination_and_scoping(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    admin = make_user(Role.SUPER_ADMIN)
    app1 = make_application(owner, status="APPROVED", officer=officer)
    app2 = make_application(owner, status="APPROVED", officer=officer)
    cert1 = _issue(client, officer, app1.id).json()["certificate"]
    cert2 = _issue(client, officer, app2.id).json()["certificate"]

    res = client.get("/api/certificates", headers=auth_header(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    numbers = {c["certificate_number"] for c in body["items"]}
    assert numbers == {cert1["certificate_number"], cert2["certificate_number"]}

    # Owner sees their own certificates too (scope_certificates -> scope_applications -> org).
    owner_res = client.get("/api/certificates", headers=auth_header(owner))
    assert owner_res.json()["total"] == 2

    other_business = make_user(Role.BUSINESS)
    assert client.get("/api/certificates", headers=auth_header(other_business)).json()["total"] == 0

    paged = client.get("/api/certificates?page_size=1", headers=auth_header(admin)).json()
    assert len(paged["items"]) == 1 and paged["total"] == 2


def test_list_certificates_status_filter(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    admin = make_user(Role.SUPER_ADMIN)
    app = make_application(owner, status="APPROVED", officer=officer)
    _issue(client, officer, app.id)

    valid = client.get("/api/certificates?status=VALID", headers=auth_header(admin)).json()
    assert valid["total"] == 1

    revoked = client.get("/api/certificates?status=REVOKED", headers=auth_header(admin)).json()
    assert revoked["total"] == 0
