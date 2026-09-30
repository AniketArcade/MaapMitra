import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, Sequence, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk

# Created by hand in migration 0006 (autogenerate ignores sequences).
certificate_number_seq = Sequence("certificate_number_seq", metadata=Base.metadata)


class CertificateStatus(StrEnum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


class Certificate(UUIDPk, Timestamps, Base):
    """One per application, created once at issuance (step 8) and never altered afterward except
    by the expiry job (step 10, VALID -> EXPIRED, plus the reminder_*_sent_at columns), a revoke
    action (not yet built), or `services/certificates.py: issue()` superseding it (step 13) when a
    later certificate is issued for the same instrument.
    `snapshot` freezes the instrument/business fields shown on the PDF at issuance time, since the
    instrument's identity/location fields unlock once the application reaches this terminal status
    (core/instrument_lock.py) — a live join would let a later edit silently change what an
    already-issued certificate displays."""

    __tablename__ = "certificates"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    certificate_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, name="certificate_status"),
        nullable=False,
        server_default=CertificateStatus.VALID.value,
    )
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    data_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Set only once the corresponding reminder has actually been emailed (step 10). NULL means
    # "not yet sent" — the idempotency mechanism for the expiry job.
    reminder_30d_sent_at: Mapped[date | None] = mapped_column(Date)
    reminder_7d_sent_at: Mapped[date | None] = mapped_column(Date)
    # Superseding chain (step 13): set by services/certificates.py: issue() in the same
    # transaction as the new certificate's insert, never by any other code path. ON DELETE
    # SET NULL — a certificate is never hard-deleted by this relationship (certificates aren't
    # hard-deleted at all today, but the FK shouldn't assume that forever).
    supersedes_certificate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("certificates.id", ondelete="SET NULL"),
    )
    superseded_by_certificate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("certificates.id", ondelete="SET NULL"),
    )
