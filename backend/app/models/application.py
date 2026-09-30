import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Sequence, Text, and_, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.core.application_types import TERMINAL_STATUSES, ApplicationStatus, ApplicationType
from app.core.verification_types import VerificationMode
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk
from app.models.instrument import Instrument
from app.models.organization import Organization
from app.models.user import User

# Created by hand in migration 0003 (autogenerate ignores sequences).
application_number_seq = Sequence("application_number_seq", metadata=Base.metadata)

ACTIVE_INDEX = "ux_applications_active_instrument"
_status_enum = Enum(ApplicationStatus, name="application_status")


class Application(UUIDPk, Timestamps, Base):
    __tablename__ = "applications"

    application_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    application_type: Mapped[ApplicationType] = mapped_column(
        Enum(ApplicationType, name="application_type"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        _status_enum, nullable=False, server_default=ApplicationStatus.DRAFT.value
    )
    # Snapshot of the instrument's location at creation (locked while the application is active).
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    district_code: Mapped[str] = mapped_column(Text, nullable=False)
    # Spec 14: snapshot of instrument.transportable at creation (same "why" as the state/district
    # snapshot above — the instrument's transportability could change later, but this application
    # freezes whatever was true when it was filed). Nullable: applications created before
    # migration 0009 have no snapshot to backfill (the whole point is it can't be reconstructed
    # after the fact); every application created from here on always gets one.
    verification_mode: Mapped[VerificationMode | None] = mapped_column(
        Enum(VerificationMode, name="verification_mode")
    )
    business_notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    instrument: Mapped[Instrument] = relationship(lazy="raise")
    organization: Mapped[Organization] = relationship(lazy="raise")
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        lazy="raise",
        back_populates="application",
        order_by="Document.created_at",
        passive_deletes=True,
    )
    history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        lazy="raise", order_by="ApplicationStatusHistory.created_at", passive_deletes=True
    )
    inspection: Mapped["Inspection | None"] = relationship(  # noqa: F821
        lazy="raise", uselist=False, passive_deletes=True
    )
    certificate: Mapped["Certificate | None"] = relationship(  # noqa: F821
        lazy="raise", uselist=False, passive_deletes=True
    )
    # Spec 12: created lazily by POST /applications/{id}/mock-pay, unlike inspection/certificate
    # above (both created by the lifecycle itself) — most applications never get a row at all.
    payment: Mapped["Payment | None"] = relationship(  # noqa: F821
        lazy="raise", uselist=False, passive_deletes=True
    )

    __table_args__ = (
        # One active (non-terminal) application per instrument. Race-free.
        Index(
            ACTIVE_INDEX,
            "instrument_id",
            unique=True,
            postgresql_where=text("status NOT IN ('REJECTED', 'CERTIFICATE_ISSUED')"),
        ),
        Index("ix_applications_org_created", "organization_id", "created_at"),
        Index("ix_applications_region_status", "state_code", "district_code", "status"),
    )


class ApplicationStatusHistory(UUIDPk, Base):
    """Append-only status timeline (feeds the application page)."""

    __tablename__ = "application_status_history"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(_status_enum)
    to_status: Mapped[ApplicationStatus] = mapped_column(_status_enum, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor: Mapped[User] = relationship(lazy="raise")


# At most one row thanks to ACTIVE_INDEX, so this is a scalar LEFT JOIN.
Instrument.active_application = relationship(
    Application,
    primaryjoin=and_(
        foreign(Application.instrument_id) == Instrument.id,
        Application.status.notin_(TERMINAL_STATUSES),
    ),
    uselist=False,
    viewonly=True,
    lazy="raise",
)
