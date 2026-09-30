import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk


class ChecklistResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"


class InspectionChecklistItem(UUIDPk, Timestamps, Base):
    """One row per CHECKLIST_TEMPLATES entry for the instrument's type, snapshotted when the
    inspection starts (app/core/inspection_templates.py). A later template edit never changes
    an in-progress or already-submitted inspection."""

    __tablename__ = "inspection_checklist_items"
    __table_args__ = (UniqueConstraint("inspection_id", "item_key"),)

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False
    )
    item_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[ChecklistResult | None] = mapped_column(
        Enum(ChecklistResult, name="checklist_result")
    )
    remarks: Mapped[str | None] = mapped_column(Text)


class InspectionMeasurement(UUIDPk, Timestamps, Base):
    """One row per MEASUREMENT_TEMPLATES fraction for the instrument's type, snapshotted when
    the inspection starts: expected_value = instrument.capacity * fraction, unit =
    instrument.capacity_unit at that moment (app/core/inspection_templates.py)."""

    __tablename__ = "inspection_measurements"
    __table_args__ = (UniqueConstraint("inspection_id", "label"),)

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Numeric(12, 3))
