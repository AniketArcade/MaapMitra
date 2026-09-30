import hashlib
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.application_types import ApplicationStatus
from app.core.certificate_status import effective_status
from app.core.config import get_settings
from app.core.errors import BadGateway, Conflict, Forbidden, NotFound
from app.core.regions import REGIONS
from app.core.roles import Role
from app.email import EmailError, get_email
from app.models.application import Application
from app.models.certificate import Certificate, CertificateStatus, certificate_number_seq
from app.models.user import User
from app.pdf.certificate import render
from app.services import applications as applications_service
from app.services import audit
from app.services.scoping import scope_certificates
from app.storage import StorageError, get_storage

log = logging.getLogger(__name__)

SIGNED_URL_SECONDS = 300  # never more than 5 minutes
S = ApplicationStatus


def _now() -> datetime:
    return datetime.now(UTC)


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29 landing on a non-leap year
        return d.replace(month=2, day=28, year=d.year + years)


def _next_certificate_number(db: Session) -> str:
    seq = db.scalar(select(certificate_number_seq.next_value()))
    return f"LM-CERT-{_now().year}-{seq:06d}"


def _snapshot(application: Application) -> dict:
    i = application.instrument
    approved_by_name = next(
        (h.actor.full_name for h in reversed(application.history) if h.to_status == S.APPROVED),
        "",
    )
    return {
        "instrument_uid": i.instrument_uid,
        "instrument_type": i.instrument_type.value,
        "manufacturer": i.manufacturer,
        "model": i.model,
        "serial_number": i.serial_number,
        "capacity": float(i.capacity),
        "capacity_unit": i.capacity_unit.value,
        "accuracy_class": i.accuracy_class.value if i.accuracy_class else None,
        "address": i.address,
        "state_name": REGIONS[i.state_code]["name"],
        "district_name": REGIONS[i.state_code]["districts"][i.district_code],
        "organization_name": application.organization.name,
        "application_number": application.application_number,
        "approved_by_name": approved_by_name,
    }


def _data_hash(
    *,
    certificate_number: str,
    snapshot: dict,
    valid_from: date,
    valid_until: date,
) -> str:
    payload = "|".join(
        [
            certificate_number,
            snapshot["instrument_uid"],
            snapshot["manufacturer"],
            snapshot["model"],
            snapshot["serial_number"],
            snapshot["organization_name"],
            valid_from.isoformat(),
            valid_until.isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def issue(db: Session, user: User, application_id: uuid.UUID, *, ip: str) -> Application:
    """Renders and stores the PDF, then atomically inserts the Certificate row and flips the
    application to CERTIFICATE_ISSUED. Mirrors documents.py: upload()'s lock ordering — the
    expensive/external work (PDF render, storage.put) happens outside any row lock; the
    application row is then locked, re-checked and the insert committed (spec 08 §4). Step 13:
    also supersedes the instrument's previous certificate (if any, and not already SUPERSEDED) in
    the same transaction — see the locking comment below."""
    application = applications_service.load(db, user, application_id, detail=True)
    if user.role != Role.LM_OFFICER:
        raise Forbidden("Insufficient permissions")
    if application.status != S.APPROVED:
        raise Conflict("Application must be approved before a certificate can be issued")

    certificate_number = _next_certificate_number(db)
    snapshot = _snapshot(application)
    valid_from = clock.today()
    valid_until = _add_years(valid_from, get_settings().CERTIFICATE_VALIDITY_YEARS)
    data_hash = _data_hash(
        certificate_number=certificate_number,
        snapshot=snapshot,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    verify_url = f"{get_settings().PUBLIC_BASE_URL}/verify/{certificate_number}"
    pdf_bytes = render(
        snapshot,
        certificate_number=certificate_number,
        valid_from=valid_from,
        valid_until=valid_until,
        data_hash=data_hash,
        verify_url=verify_url,
    )

    certificate_id = uuid.uuid4()
    pdf_path = f"certificates/{certificate_id}.pdf"
    db.commit()  # end the read transaction; nothing is held while the PDF uploads

    storage = get_storage()
    try:
        storage.put(pdf_path, pdf_bytes, "application/pdf")
    except StorageError:
        raise BadGateway("Certificate storage failed, please retry") from None

    try:
        # Re-check under the application row lock: a concurrent double-click race guard.
        # populate_existing: without it the identity map returns the stale pre-lock copy
        # (this `application`/`locked` object may already be cached from the load() above).
        locked = db.scalar(
            select(Application)
            .where(Application.id == application.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None or locked.status != S.APPROVED:
            raise Conflict("Application must be approved before a certificate can be issued")

        # Step 13: supersede the instrument's most recent certificate (any status), if it isn't
        # already SUPERSEDED, inside this same transaction/lock — never a second commit. Locked
        # with `of=Certificate` (the joined Application row is already locked above) under the
        # same populate_existing discipline: a concurrent second issuance racing to supersede the
        # same previous certificate must serialize on this row too, not just on the application.
        previous = db.scalar(
            select(Certificate)
            .join(Application, Application.id == Certificate.application_id)
            .where(Application.instrument_id == locked.instrument_id)
            .order_by(Certificate.created_at.desc())
            .limit(1)
            .with_for_update(of=Certificate)
            .execution_options(populate_existing=True)
        )
        supersede_previous = previous is not None and previous.status != (
            CertificateStatus.SUPERSEDED
        )
        supersedes_id = previous.id if supersede_previous else None

        certificate = Certificate(
            id=certificate_id,
            application_id=locked.id,
            organization_id=locked.organization_id,
            certificate_number=certificate_number,
            snapshot=snapshot,
            valid_from=valid_from,
            valid_until=valid_until,
            status=CertificateStatus.VALID,
            pdf_path=pdf_path,
            data_hash=data_hash,
            supersedes_certificate_id=supersedes_id,
        )
        db.add(certificate)
        # Flush the INSERT before the previous row's UPDATE below: both are plain scalar FK
        # values (certificate_id was generated client-side above, not a post-insert PK), so
        # SQLAlchemy's unit-of-work has no relationship to infer the ordering from and may
        # otherwise emit the UPDATE first — which Postgres's (non-deferred) FK constraint would
        # reject, since superseded_by_certificate_id would point at a row that doesn't exist yet.
        if supersede_previous:
            db.flush()
            previous.status = CertificateStatus.SUPERSEDED
            previous.superseded_by_certificate_id = certificate_id

        applications_service.apply_certificate_issued(db, locked, user, ip=ip)
        audit.log(
            db,
            actor=user,
            action="CERTIFICATE_ISSUED",
            entity_type="certificate",
            entity_id=certificate_id,
            organization_id=locked.organization_id,
            details={
                "certificate_number": certificate_number,
                "valid_until": valid_until.isoformat(),
                "data_hash": data_hash,
                "supersedes_certificate_id": str(supersedes_id) if supersedes_id else None,
            },
            ip=ip,
        )
        db.commit()
    except BaseException:
        db.rollback()
        applications_service.delete_objects_best_effort([pdf_path])  # accepted: rare orphans
        raise
    return locked


def get(db: Session, user: User, certificate_id: uuid.UUID) -> Certificate:
    """One scoped query: out of scope (incl. wrong org/jurisdiction) is 404, never 403."""
    certificate = db.scalar(
        scope_certificates(select(Certificate), user).where(Certificate.id == certificate_id)
    )
    if certificate is None:
        raise NotFound("Certificate not found")
    return certificate


def signed_url(
    db: Session, user: User, certificate_id: uuid.UUID, *, download: bool = False, ip: str
) -> str:
    """download=False: the link displays the PDF inline (View). True: it saves the file under
    the certificate number (Download)."""
    certificate = get(db, user, certificate_id)
    try:
        url = get_storage().signed_url(
            certificate.pdf_path,
            SIGNED_URL_SECONDS,
            f"{certificate.certificate_number}.pdf" if download else None,
        )
    except StorageError:
        raise BadGateway("Could not create a download link, please retry") from None
    audit.log(
        db,
        actor=user,
        action="CERTIFICATE_URL_ISSUED",
        entity_type="certificate",
        entity_id=certificate.id,
        organization_id=certificate.organization_id,
        details={
            "certificate_number": certificate.certificate_number,
            "disposition": "attachment" if download else "inline",
        },
        ip=ip,
    )
    db.commit()  # audit-writing GET: the service commits (spec 03 §2.4)
    return url


def public_verify(db: Session, certificate_number: str) -> Certificate:
    """No scope check: deliberately public (spec 09 §2). One indexed lookup, no joins — every
    field PublicVerifyOut needs already lives on this row (spec 08 §3.1's snapshot)."""
    certificate = db.scalar(
        select(Certificate).where(Certificate.certificate_number == certificate_number)
    )
    if certificate is None:
        raise NotFound("Certificate not found")
    return certificate


def _recipients(db: Session, certificate: Certificate) -> list[str]:
    """The org's BUSINESS user(s) — ordinarily exactly one, but not DB-enforced (spec 10 §4.1),
    so every match is emailed and zero matches is tolerated by the caller."""
    return list(
        db.scalars(
            select(User.email).where(
                User.organization_id == certificate.organization_id, User.role == Role.BUSINESS
            )
        )
    )


def _reminder_email_body(certificate: Certificate, *, urgent: bool) -> tuple[str, str]:
    s = certificate.snapshot
    instrument = f"{s['manufacturer']} {s['model']} (S/N {s['serial_number']})"
    subject = (
        f"{'Urgent: ' if urgent else ''}Certificate {certificate.certificate_number} "
        f"expires {certificate.valid_until.isoformat()}"
    )
    body = (
        f"Certificate {certificate.certificate_number} for {instrument} "
        f"expires on {certificate.valid_until.isoformat()}. "
        f"Log in at {get_settings().PUBLIC_BASE_URL}/login to start a new verification "
        "application before it expires."
    )
    return subject, body


def _try_send_reminder(certificate: Certificate, recipients: list[str], *, urgent: bool) -> bool:
    """True if every recipient was sent the email. Never raises: a failure is the caller's
    signal to leave reminder_*_sent_at unset so the next run retries."""
    subject, body = _reminder_email_body(certificate, urgent=urgent)
    email = get_email()
    try:
        for to in recipients:
            email.send(to=to, subject=subject, body=body)
    except EmailError:
        log.warning("expiry reminder send failed for %s", certificate.certificate_number)
        return False
    return True


def expiry_check(db: Session) -> dict[str, int]:
    """Daily job (step 10, spec 10 §4): sends reminder emails at two thresholds and flips
    VALID -> EXPIRED once valid_until has passed. Idempotent via reminder_*_sent_at (only set on
    a successful send) — a second run the same day, or a run that's late by weeks, always does
    exactly the work that's still outstanding, nothing more."""
    today = clock.today()
    settings = get_settings()
    summary = {
        "checked": 0,
        "reminders_30d_sent": 0,
        "reminders_7d_sent": 0,
        "expired": 0,
        "email_failures": 0,
        "skipped_no_recipient": 0,
    }

    certificates = db.scalars(
        select(Certificate).where(Certificate.status == CertificateStatus.VALID)
    )
    for certificate in certificates:
        summary["checked"] += 1
        try:
            days_30, days_7 = settings.EXPIRY_REMINDER_30D_DAYS, settings.EXPIRY_REMINDER_7D_DAYS
            needs_30d = (
                certificate.reminder_30d_sent_at is None
                and certificate.valid_until <= today + timedelta(days=days_30)
            )
            needs_7d = (
                certificate.reminder_7d_sent_at is None
                and certificate.valid_until <= today + timedelta(days=days_7)
            )

            if needs_30d or needs_7d:
                recipients = _recipients(db, certificate)
                if not recipients:
                    summary["skipped_no_recipient"] += 1
                else:
                    if needs_30d:
                        if _try_send_reminder(certificate, recipients, urgent=False):
                            certificate.reminder_30d_sent_at = today
                            summary["reminders_30d_sent"] += 1
                            db.commit()
                        else:
                            summary["email_failures"] += 1
                    if needs_7d:
                        if _try_send_reminder(certificate, recipients, urgent=True):
                            certificate.reminder_7d_sent_at = today
                            summary["reminders_7d_sent"] += 1
                            db.commit()
                        else:
                            summary["email_failures"] += 1

            # Reuses the same rule the public verify page already displays live (spec 09) —
            # the only difference here is that the result is actually persisted.
            if effective_status(certificate.status, certificate.valid_until, today=today) == (
                CertificateStatus.EXPIRED
            ):
                certificate.status = CertificateStatus.EXPIRED
                audit.log(
                    db,
                    actor=None,
                    action="CERTIFICATE_EXPIRED",
                    entity_type="certificate",
                    entity_id=certificate.id,
                    organization_id=certificate.organization_id,
                    details={
                        "certificate_number": certificate.certificate_number,
                        "valid_until": certificate.valid_until.isoformat(),
                    },
                )
                summary["expired"] += 1
                db.commit()
        except Exception:
            db.rollback()
            log.exception("expiry_check failed for certificate %s", certificate.id)

    return summary
