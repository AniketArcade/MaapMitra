import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk
from app.models.user import User


class Inspection(UUIDPk, Timestamps, Base):
    """Scheduling and field-inspection record for an application (steps 5-6).

    One per application (unique FK): a reschedule updates this row, it never creates a new
    one. No `status` column — the application's own `status` stays the single source of
    truth. `submitted_at IS NOT NULL` is the single source of truth for "this inspection's
    checklist is locked" (step 6); the checklist items and measurements themselves live in
    `inspection_checklist_items` / `inspection_measurements` (app/models/inspection_checklist.py).
    """

    __tablename__ = "inspections"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Self-assign only in step 5 (D2): always the officer who scheduled it. Also the only
    # officer who may start, edit and submit the inspection in step 6 (spec 06 D1).
    assigned_officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    overall_remarks: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )

    assigned_officer: Mapped[User] = relationship(lazy="raise", foreign_keys=[assigned_officer_id])

    __table_args__ = (
        Index("ix_inspections_officer_date", "assigned_officer_id", "scheduled_date"),
    )
