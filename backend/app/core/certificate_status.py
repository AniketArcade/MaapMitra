from datetime import date

from app.models.certificate import CertificateStatus


def effective_status(
    status: CertificateStatus, valid_until: date, *, today: date
) -> CertificateStatus:
    """Single source of truth for "what status should a viewer see right now," independent of
    whether step 10's expiry cron has run yet. REVOKED always wins: a revoke is permanent, never
    displayed as merely expired even if also past valid_until (spec 09 §4)."""
    if status == CertificateStatus.REVOKED:
        return CertificateStatus.REVOKED
    if valid_until < today:
        return CertificateStatus.EXPIRED
    return status
