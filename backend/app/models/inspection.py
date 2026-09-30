import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk
from app.models.user import User


class Inspection(UUIDPk, Timestamps, Base):
    """Scheduling record for an application's field inspection (step 5).

    One per application (unique FK): a reschedule updates this row, it never creates a new
    one. No `status` column — the application's own `status` stays the single source of
    truth; step 6 adds checklist/measurement data here.
    """

    __tablename__ = "inspections"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Self-assign only in step 5 (D2): always the officer who scheduled it.
    assigned_officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    assigned_officer: Mapped[User] = relationship(lazy="raise")

    __table_args__ = (
        Index("ix_inspections_officer_date", "assigned_officer_id", "scheduled_date"),
    )
