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


class StateOverviewRow(BaseModel):
    """Spec 17 §6.4: one row per REGIONS state/UT (~36), always present and zero-filled when a
    state has no data yet — the Phase 1 substitute for the brief's India map (root CLAUDE.md's
    Deferred list names Leaflet maps explicitly)."""

    state_code: str
    state_name: str
    instrument_count: int
    pending_applications: int
    certs_valid: int
    certs_expired: int
