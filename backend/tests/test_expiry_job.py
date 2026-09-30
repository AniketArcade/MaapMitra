"""Spec 10: the daily expiry job (POST /api/jobs/expiry-check + services/certificates.py:
expiry_check()). Reminder thresholds, idempotency, the VALID -> EXPIRED flip, and that one
certificate's failure (bad email, no recipient) never blocks another's."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.core.roles import Role
from app.db.session import SessionLocal
from app.email import EmailError
from app.models import Certificate, User
from app.models.certificate import CertificateStatus
from app.services import certificates as certificates_service
from tests.conftest import auth_header
from tests.helpers import audit_rows

FROZEN = datetime(2026, 10, 14, 20, 0, tzinfo=UTC)  # = 2026-10-15 01:30 IST


@pytest.fixture
def frozen_today(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    monkeypatch.setattr(clock, "now_utc", lambda: FROZEN)
    return clock.today()


def _issue(client: TestClient, officer, application_id) -> dict:  # noqa: ANN001
    res = client.post(
        f"/api/applications/{application_id}/certificate", headers=auth_header(officer)
    )
    assert res.status_code == 200, res.text
    return res.json()["certificate"]


def _run(client: TestClient) -> dict:
    res = client.post("/api/jobs/expiry-check", headers={"X-Cron-Secret": "test-cron-secret"})
    assert res.status_code == 200, res.text
    return res.json()


def _set_valid_until(certificate_id: str, valid_until, **extra) -> None:  # noqa: ANN001
    with SessionLocal() as s:
        row = s.get(Certificate, certificate_id)
        assert row is not None
        row.valid_until = valid_until
        for k, v in extra.items():
            setattr(row, k, v)
        s.commit()


def test_expiry_check_requires_secret(client: TestClient) -> None:
    assert client.post("/api/jobs/expiry-check").status_code == 401
    assert (
        client.post("/api/jobs/expiry-check", headers={"X-Cron-Secret": "wrong"}).status_code == 401
    )
    with SessionLocal() as s:
        assert s.query(Certificate).count() == 0


def test_expiry_check_30d_reminder(
    client: TestClient, make_user, make_application, frozen_today, email
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    _set_valid_until(cert["id"], frozen_today + timedelta(days=30))

    summary = _run(client)
    assert summary["reminders_30d_sent"] == 1
    assert summary["reminders_7d_sent"] == 0
    assert summary["expired"] == 0
    assert len(email.sent) == 1

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
    assert row.reminder_30d_sent_at == frozen_today
    assert row.reminder_7d_sent_at is None
    assert row.status == CertificateStatus.VALID


def test_expiry_check_7d_reminder(
    client: TestClient, make_user, make_application, frozen_today, email
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    # Past the 30-day window already (simulates that reminder having been sent earlier).
    _set_valid_until(
        cert["id"], frozen_today + timedelta(days=7), reminder_30d_sent_at=frozen_today
    )

    summary = _run(client)
    assert summary["reminders_30d_sent"] == 0
    assert summary["reminders_7d_sent"] == 1
    assert len(email.sent) == 1

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
    assert row.reminder_7d_sent_at == frozen_today


def test_expiry_check_catchup_sends_both_and_expires(
    client: TestClient, make_user, make_application, frozen_today, email
) -> None:  # noqa: ANN001
    """A certificate the job hasn't touched in a month: both reminders (never sent) and the
    expiry flip all happen in a single run."""
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    _set_valid_until(cert["id"], frozen_today - timedelta(days=2))

    summary = _run(client)
    assert summary["reminders_30d_sent"] == 1
    assert summary["reminders_7d_sent"] == 1
    assert summary["expired"] == 1
    assert len(email.sent) == 2

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
    assert row.status == CertificateStatus.EXPIRED
    assert row.reminder_30d_sent_at == frozen_today
    assert row.reminder_7d_sent_at == frozen_today

    expired_rows = audit_rows("CERTIFICATE_EXPIRED")
    assert len(expired_rows) == 1
    assert expired_rows[0].details["certificate_number"] == cert["certificate_number"]
    assert expired_rows[0].actor_user_id is None


def test_expiry_check_idempotent(
    client: TestClient, make_user, make_application, frozen_today, email
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    _set_valid_until(cert["id"], frozen_today + timedelta(days=10))

    first = _run(client)
    assert first["reminders_30d_sent"] == 1
    assert first["reminders_7d_sent"] == 0  # 10 days out is within the 30d window, not the 7d one

    second = _run(client)
    assert second["reminders_30d_sent"] == 0
    assert second["reminders_7d_sent"] == 0
    assert second["expired"] == 0
    assert len(email.sent) == 1  # unchanged from the first run


def test_expiry_check_revoked_never_touched(
    client: TestClient, make_user, make_application, frozen_today, email
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    _set_valid_until(
        cert["id"], frozen_today - timedelta(days=30), status=CertificateStatus.REVOKED
    )

    summary = _run(client)
    assert summary["checked"] == 0  # REVOKED is outside the job's query entirely
    assert not email.sent

    with SessionLocal() as s:
        row = s.get(Certificate, cert["id"])
    assert row.status == CertificateStatus.REVOKED
    assert audit_rows("CERTIFICATE_EXPIRED") == []


def test_expiry_check_email_failure_does_not_block_others(
    client: TestClient, make_user, make_application, frozen_today, email, monkeypatch
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    bad_owner = make_user(Role.BUSINESS, email="bad-owner@test.demo")
    good_owner = make_user(Role.BUSINESS, email="good-owner@test.demo")
    bad_app = make_application(bad_owner, status="APPROVED", officer=officer)
    good_app = make_application(good_owner, status="APPROVED", officer=officer)
    bad_cert = _issue(client, officer, bad_app.id)
    good_cert = _issue(client, officer, good_app.id)

    # bad_cert: 30d already sent earlier, so this run only attempts its 7d reminder (one send).
    _set_valid_until(
        bad_cert["id"],
        frozen_today - timedelta(days=1),
        reminder_30d_sent_at=frozen_today - timedelta(days=10),
    )
    _set_valid_until(good_cert["id"], frozen_today + timedelta(days=25))

    real_send = email.send

    def failing_send(*, to: str, subject: str, body: str) -> None:
        if to == "bad-owner@test.demo":
            raise EmailError("simulated")
        real_send(to=to, subject=subject, body=body)

    monkeypatch.setattr(email, "send", failing_send)

    summary = _run(client)
    assert summary["email_failures"] == 1
    assert summary["reminders_30d_sent"] == 1  # good_cert's
    assert summary["reminders_7d_sent"] == 0  # bad_cert's failed
    assert summary["expired"] == 1  # bad_cert still expires despite the failed email
    assert len(email.sent) == 1
    assert email.sent[0]["to"] == "good-owner@test.demo"

    with SessionLocal() as s:
        bad = s.get(Certificate, bad_cert["id"])
        good = s.get(Certificate, good_cert["id"])
    assert bad.status == CertificateStatus.EXPIRED
    assert bad.reminder_7d_sent_at is None  # retried next run
    assert good.reminder_30d_sent_at == frozen_today


def test_expiry_check_no_recipient(
    client: TestClient, make_user, make_application, frozen_today
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    other = make_user(Role.BUSINESS)  # a different organization
    app = make_application(owner, status="APPROVED", officer=officer)
    cert = _issue(client, officer, app.id)
    _set_valid_until(cert["id"], frozen_today + timedelta(days=1))

    with SessionLocal() as s:
        u = s.get(User, owner.id)
        assert u is not None
        u.organization_id = other.organization_id  # orphans the cert's org: no BUSINESS user left
        s.commit()

    summary = _run(client)
    assert summary["skipped_no_recipient"] == 1
    assert summary["reminders_30d_sent"] == 0


def test_expiry_check_service_function_empty(frozen_today) -> None:  # noqa: ANN001
    """A direct call to the service function (bypassing HTTP), with no certificates at all."""
    with SessionLocal() as s:
        summary = certificates_service.expiry_check(s)
    assert summary == {
        "checked": 0,
        "reminders_30d_sent": 0,
        "reminders_7d_sent": 0,
        "expired": 0,
        "email_failures": 0,
        "skipped_no_recipient": 0,
    }
