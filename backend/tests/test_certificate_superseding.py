"""Spec 13: certificate superseding (SUPERSEDED status + supersedes/superseded_by chain,
CertificateOut.is_expiring_soon, admin stats' `superseded` bucket, and the public-verify field
additions). Mirrors tests/test_certificates.py's style (spec 08) and reuses its
double-issue-race-guard idiom (threading + barrier) for the atomicity test.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Certificate, User
from app.models.certificate import CertificateStatus
from app.services import audit
from app.services import certificates as certificates_service
from tests.conftest import auth_header
from tests.helpers import audit_rows


def _issue(client: TestClient, officer, application_id) -> dict:  # noqa: ANN001
    res = client.post(
        f"/api/applications/{application_id}/certificate", headers=auth_header(officer)
    )
    assert res.status_code == 200, res.text
    return res.json()["certificate"]


def _get(client: TestClient, officer, certificate_id: str) -> dict:  # noqa: ANN001
    res = client.get(f"/api/certificates/{certificate_id}", headers=auth_header(officer))
    assert res.status_code == 200, res.text
    return res.json()


# --- (b) no prior certificate: both link fields stay null -----------------------------------


def test_issue_first_certificate_has_no_supersede_links(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    assert cert["supersedes_certificate_id"] is None
    assert cert["superseded_by_certificate_id"] is None
    assert cert["is_expiring_soon"] is False  # freshly issued, years from expiry


# --- (a) issuing a second certificate for the same instrument supersedes the first ----------


def test_issue_second_certificate_supersedes_first(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)

    first_app = make_application(owner, instrument, status="APPROVED", officer=officer)
    first_cert = _issue(client, officer, first_app.id)

    # CERTIFICATE_ISSUED is terminal, so a second application against the same instrument
    # (re-verification, in spirit) is allowed once the first is issued.
    second_app = make_application(owner, instrument, status="APPROVED", officer=officer)
    second_cert = _issue(client, officer, second_app.id)

    assert second_cert["supersedes_certificate_id"] == first_cert["id"]
    assert second_cert["superseded_by_certificate_id"] is None

    updated_first = _get(client, officer, first_cert["id"])
    assert updated_first["status"] == "SUPERSEDED"
    assert updated_first["superseded_by_certificate_id"] == second_cert["id"]
    assert updated_first["supersedes_certificate_id"] is None  # unchanged: it was the first
    # A superseded certificate is never "expiring soon" regardless of its own valid_until.
    assert updated_first["is_expiring_soon"] is False

    audit_detail = next(
        r for r in audit_rows("CERTIFICATE_ISSUED") if str(r.entity_id) == second_cert["id"]
    ).details
    assert audit_detail["supersedes_certificate_id"] == first_cert["id"]


def test_issue_third_certificate_chains_off_the_most_recent(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    """The chain always points at the most-recently-issued certificate, not the original one —
    and an already-superseded certificate's own links are never touched again."""
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)

    first_cert = _issue(
        client, officer, make_application(owner, instrument, status="APPROVED", officer=officer).id
    )
    second_cert = _issue(
        client, officer, make_application(owner, instrument, status="APPROVED", officer=officer).id
    )
    third_cert = _issue(
        client, officer, make_application(owner, instrument, status="APPROVED", officer=officer).id
    )

    assert third_cert["supersedes_certificate_id"] == second_cert["id"]

    first_now = _get(client, officer, first_cert["id"])
    second_now = _get(client, officer, second_cert["id"])
    assert first_now["status"] == "SUPERSEDED"
    assert first_now["superseded_by_certificate_id"] == second_cert["id"]  # untouched by the 3rd
    assert second_now["status"] == "SUPERSEDED"
    assert second_now["superseded_by_certificate_id"] == third_cert["id"]


def test_supersede_skipped_if_latest_certificate_already_superseded(
    make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    """Guards the literal condition in services/certificates.py: issue() — "if one exists and its
    status is not already SUPERSEDED". Forces the (otherwise unreachable through the normal issue()
    path) edge case where the most-recently-created certificate for an instrument is already
    SUPERSEDED, and confirms a new issuance leaves it alone rather than re-linking it."""
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)

    first_app = make_application(owner, instrument, status="APPROVED", officer=officer)
    with SessionLocal() as s:
        user = s.get(User, officer.id)
        assert user is not None
        certificates_service.issue(s, user, first_app.id, ip="test")

    with SessionLocal() as s:
        first_cert = s.scalar(select(Certificate).where(Certificate.application_id == first_app.id))
        assert first_cert is not None
        first_cert.status = CertificateStatus.SUPERSEDED  # force the edge-case state directly
        s.commit()
        first_cert_id = first_cert.id

    second_app = make_application(owner, instrument, status="APPROVED", officer=officer)
    with SessionLocal() as s:
        user = s.get(User, officer.id)
        assert user is not None
        certificates_service.issue(s, user, second_app.id, ip="test")

    with SessionLocal() as s:
        second_cert = s.scalar(
            select(Certificate).where(Certificate.application_id == second_app.id)
        )
        assert second_cert is not None
        assert second_cert.supersedes_certificate_id is None
        first_after = s.get(Certificate, first_cert_id)
        assert first_after is not None
        assert first_after.superseded_by_certificate_id is None  # left exactly as forced above


def test_supersede_atomic_on_failure(
    make_user, make_instrument, make_application, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001
    """A failure inside the transaction (after the supersede flip and the new row are staged, but
    before commit) leaves neither row half-updated — mirrors the rollback discipline
    services/certificates.py: issue() already documents for the double-issue race guard
    (tests/test_certificates.py: test_issue_certificate_double_issue_race)."""
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)

    first_app = make_application(owner, instrument, status="APPROVED", officer=officer)
    with SessionLocal() as s:
        user = s.get(User, officer.id)
        assert user is not None
        certificates_service.issue(s, user, first_app.id, ip="test")
    with SessionLocal() as s:
        first_cert = s.scalar(select(Certificate).where(Certificate.application_id == first_app.id))
        assert first_cert is not None
        first_cert_id = first_cert.id

    second_app = make_application(owner, instrument, status="APPROVED", officer=officer)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated mid-transaction failure")

    # audit.log is called (via applications_service.apply_certificate_issued) after both the
    # supersede flip and the new Certificate insert are staged, but before db.commit() —
    # exactly the "leaves neither row half-updated" window this test targets.
    monkeypatch.setattr(audit, "log", boom)

    with SessionLocal() as s:
        user = s.get(User, officer.id)
        assert user is not None
        with pytest.raises(RuntimeError, match="simulated mid-transaction failure"):
            certificates_service.issue(s, user, second_app.id, ip="test")

    with SessionLocal() as s:
        first_after = s.get(Certificate, first_cert_id)
        assert first_after is not None
        assert first_after.status == CertificateStatus.VALID  # rollback undid the supersede flip
        assert first_after.superseded_by_certificate_id is None
        count = s.scalar(
            select(func.count())
            .select_from(Certificate)
            .where(Certificate.application_id == second_app.id)
        )
        assert count == 0  # the second certificate row was never actually committed


# --- (c) is_expiring_soon via the API surface (unit coverage lives in test_certificate_status.py)


def test_certificate_out_is_expiring_soon_reflects_valid_until(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    from datetime import timedelta

    from app.core import clock
    from app.core.config import get_settings

    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)

    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
        assert row is not None
        row.valid_until = clock.today() + timedelta(days=horizon)
        s.commit()

    assert _get(client, officer, cert["id"])["is_expiring_soon"] is True


# --- (f) admin stats' superseded bucket: tests/test_admin_certificates.py
# --- (e) public verify's new fields / non-leakage: tests/test_public_verify.py
