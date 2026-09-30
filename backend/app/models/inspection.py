import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.gatc_types import InspectionAssigneeRole
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk
from app.models.user import User


class Inspection(UUIDPk, Timestamps, Base):
    """Scheduling and field-inspection record for an application (steps 5-6, extended step 15).

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
    # Self-assign (LM_OFFICER) in step 5 (D2), or a specific GATC-role user in the same org
    # picked by the scheduling officer (step 15) — either way, "a specific person", not a role or
    # an org. Also the only person who may start, edit and submit the inspection in step 6/15.
    assigned_officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Spec 15: denormalized copy of assigned_officer's role at the moment of assignment (avoids a
    # join to users.role for reporting/dashboards). Set once, here, when the Inspection row is
    # created (services/applications.py: transition()'s SCHEDULED branch) — never re-validated
    # afterward, because nothing in this codebase ever changes a user's role after creation (no
    # such endpoint exists; confirmed by reading every services/users.py / routers/users.py write
    # path), so it cannot go stale against a role change that can never happen.
    assignee_role: Mapped[InspectionAssigneeRole] = mapped_column(
        Enum(InspectionAssigneeRole, name="inspection_assignee_role"), nullable=False
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
