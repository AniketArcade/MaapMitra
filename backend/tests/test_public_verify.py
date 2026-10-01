"""Spec 09: public certificate verification (GET /api/public/verify/{certificate_number}).

Every request in this file deliberately omits auth_header(...) (or, where noted, uses an
unrelated user's) since the whole point of this endpoint is that it needs none.
"""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import clock
from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Certificate
from app.models.certificate import CertificateStatus
from tests.conftest import auth_header

FIELDS = {
    "certificate_number",
    "status",
    "instrument_type_label",
    "instrument_uid",
    "manufacturer",
    "model",
    "serial_number",
    "valid_from",
    "valid_until",
    "issued_by",
}


def _issue(client: TestClient, officer, application_id) -> dict:  # noqa: ANN001
    res = client.post(
        f"/api/applications/{application_id}/certificate", headers=auth_header(officer)
    )
    assert res.status_code == 200, res.text
    return res.json()["certificate"]


def test_public_verify_success(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    res = client.get(f"/api/public/verify/{cert['certificate_number']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body.keys()) == FIELDS
    assert body["certificate_number"] == cert["certificate_number"]
    assert body["status"] == "VALID"
    assert body["instrument_type_label"] == "Weighing scale"
    assert body["instrument_uid"] == cert["instrument_uid"]
    assert body["manufacturer"] == cert["manufacturer"]
    assert body["model"] == cert["model"]
    assert body["serial_number"] == cert["serial_number"]
    assert body["valid_from"] == cert["valid_from"]
    assert body["valid_until"] == cert["valid_until"]
    assert body["issued_by"] == officer.full_name


def test_public_verify_not_found(client: TestClient) -> None:
    res = client.get("/api/public/verify/LM-CERT-2026-999999")
    assert (res.status_code, res.json()["detail"]) == (404, "Certificate not found")


def test_public_verify_live_expired(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
        assert row is not None
        row.valid_until = clock.today() - timedelta(days=1)
        assert row.status == CertificateStatus.VALID  # stored status untouched: no cron ran
        s.commit()

    res = client.get(f"/api/public/verify/{cert['certificate_number']}")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "EXPIRED"


def test_public_verify_revoked_beats_expired(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
        assert row is not None
        row.valid_until = clock.today() - timedelta(days=1)
        row.status = CertificateStatus.REVOKED
        s.commit()

    res = client.get(f"/api/public/verify/{cert['certificate_number']}")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "REVOKED"


def test_public_verify_superseded_status(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    """Spec 13: a superseded certificate's own `status` is the signal the public page shows —
    no supersedes/superseded_by chain field is ever exposed here (see FIELDS above)."""
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
        assert row is not None
        row.status = CertificateStatus.SUPERSEDED
        s.commit()

    res = client.get(f"/api/public/verify/{cert['certificate_number']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "SUPERSEDED"
    assert set(body.keys()) == FIELDS  # still exactly the authorized field set, nothing extra


def test_public_verify_truly_public(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    no_auth = client.get(f"/api/public/verify/{cert['certificate_number']}").json()
    with_business = client.get(
        f"/api/public/verify/{cert['certificate_number']}",
        headers=auth_header(make_user(Role.BUSINESS)),
    ).json()
    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    with_outsider = client.get(
        f"/api/public/verify/{cert['certificate_number']}", headers=auth_header(outsider)
    ).json()
    assert no_auth == with_business == with_outsider


def test_public_verify_rate_limit(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    for _ in range(30):
        res = client.get(f"/api/public/verify/{cert['certificate_number']}")
        assert res.status_code == 200
    res = client.get(f"/api/public/verify/{cert['certificate_number']}")
    assert res.status_code == 429


def test_public_regions_no_auth(client: TestClient) -> None:
    res = client.get("/api/public/regions")
    assert res.status_code == 200
    regions = res.json()
    state_codes = {r["state_code"] for r in regions}
    assert "JH" in state_codes
    assert len(regions) >= 36  # all states + UTs
    jh = next(r for r in regions if r["state_code"] == "JH")
    assert {d["code"] for d in jh["districts"]} == {"DHN", "RNC", "BKR"}
