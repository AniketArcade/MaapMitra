from datetime import date, timedelta

from app.core.config import get_settings
from app.models.certificate import CertificateStatus


def effective_status(
    status: CertificateStatus, valid_until: date, *, today: date
) -> CertificateStatus:
    """Single source of truth for "what status should a viewer see right now," independent of
    whether step 10's expiry cron has run yet. REVOKED always wins: a revoke is permanent, never
    displayed as merely expired even if also past valid_until (spec 09 §4).

    Unchanged by step 13: SUPERSEDED is not special-cased here, on purpose — it falls through the
    same "valid_until < today -> EXPIRED" rule every non-REVOKED status already gets. Adding a
    SUPERSEDED-wins branch would change this function's existing return values for certificates
    that are both superseded and past their date, which is exactly the contract step 13 was told
    not to touch. See is_expiring_soon() below for the strictly additive piece of step 13."""
    if status == CertificateStatus.REVOKED:
        return CertificateStatus.REVOKED
    if valid_until < today:
        return CertificateStatus.EXPIRED
    return status


def is_expiring_soon(status: CertificateStatus, valid_until: date, *, today: date) -> bool:
    """Additive sibling to effective_status() (step 13) — never changes what that function itself
    returns. True only when the certificate currently reads as VALID (via effective_status(), so
    REVOKED/EXPIRED/SUPERSEDED are always False here even if valid_until happens to fall inside
    the window) and valid_until is within EXPIRY_REMINDER_30D_DAYS of today. Reuses the same
    threshold the reminder job and the admin stats endpoint already key off
    (services/certificates.py: expiry_check(), services/admin.py: certificate_stats())."""
    if effective_status(status, valid_until, today=today) != CertificateStatus.VALID:
        return False
    return valid_until <= today + timedelta(days=get_settings().EXPIRY_REMINDER_30D_DAYS)
