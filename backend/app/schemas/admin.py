from typing import Self

from pydantic import BaseModel

from app.models.certificate import CertificateStatus


class AdminCertificateStats(BaseModel):
    valid: int  # includes valid-and-expiring-soon; not a disjoint bucket
    expiring_soon: int  # VALID and valid_until <= today + EXPIRY_REMINDER_30D_DAYS
    expired: int
    revoked: int
    superseded: int  # step 13

    @classmethod
    def from_counts(cls, by_status: dict[CertificateStatus, int], expiring_soon: int) -> Self:
        return cls(
            valid=by_status.get(CertificateStatus.VALID, 0),
            expiring_soon=expiring_soon,
            expired=by_status.get(CertificateStatus.EXPIRED, 0),
            revoked=by_status.get(CertificateStatus.REVOKED, 0),
            superseded=by_status.get(CertificateStatus.SUPERSEDED, 0),
        )
