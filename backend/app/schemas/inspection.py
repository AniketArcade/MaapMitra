import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field

from app.core.application_types import MAX_EVIDENCE_PHOTOS
from app.core.gatc_types import InspectionAssigneeRole
from app.core.inspection_templates import (
    CHECKLIST_TEMPLATES,
    MEASUREMENT_TEMPLATES,
    measurement_label,
)
from app.core.instrument_types import InstrumentType
from app.models.inspection import Inspection
from app.models.inspection_checklist import (
    ChecklistResult,
    InspectionChecklistItem,
    InspectionMeasurement,
)
from app.models.user import User
from app.schemas.application import Notes
from app.schemas.common import StrictModel
from app.schemas.document import DocumentOut

ObservedValue = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class ChecklistItemUpdate(StrictModel):
    item_key: str
    result: ChecklistResult | None = None
    remarks: Notes | None = None


class MeasurementUpdate(StrictModel):
    label: str
    observed_value: ObservedValue | None = None


class InspectionUpdate(StrictModel):
    """Partial: only the list entries present are applied; other rows are untouched."""

    checklist_items: list[ChecklistItemUpdate] | None = None
    measurements: list[MeasurementUpdate] | None = None
    overall_remarks: Notes | None = None


class ChecklistItemOut(BaseModel):
    item_key: str
    label: str
    result: ChecklistResult | None
    remarks: str | None

    @classmethod
    def from_model(cls, item: InspectionChecklistItem) -> Self:
        return cls(
            item_key=item.item_key, label=item.label, result=item.result, remarks=item.remarks
        )


class MeasurementOut(BaseModel):
    label: str
    unit: str
    expected_value: float
    observed_value: float | None

    @classmethod
    def from_model(cls, m: InspectionMeasurement) -> Self:
        return cls(
            label=m.label,
            unit=m.unit,
            expected_value=float(m.expected_value),
            observed_value=float(m.observed_value) if m.observed_value is not None else None,
        )


class InspectionDetail(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_date: date
    assigned_officer_name: str
    assignee_role: InspectionAssigneeRole  # spec 15
    checklist_items: list[ChecklistItemOut]
    measurements: list[MeasurementOut]
    evidence: list[DocumentOut]
    overall_remarks: str | None
    submitted_at: datetime | None
    can_edit: bool  # caller is the assigned officer and submitted_at is None

    @classmethod
    def build(
        cls,
        inspection: Inspection,
        *,
        checklist_items: list[InspectionChecklistItem],
        measurements: list[InspectionMeasurement],
        evidence: list[DocumentOut],
        user: User,
    ) -> Self:
        return cls(
            id=inspection.id,
            application_id=inspection.application_id,
            scheduled_date=inspection.scheduled_date,
            assigned_officer_name=inspection.assigned_officer.full_name,
            assignee_role=inspection.assignee_role,
            checklist_items=[ChecklistItemOut.from_model(i) for i in checklist_items],
            measurements=[MeasurementOut.from_model(m) for m in measurements],
            evidence=evidence,
            overall_remarks=inspection.overall_remarks,
            submitted_at=inspection.submitted_at,
            can_edit=(
                inspection.assigned_officer_id == user.id and inspection.submitted_at is None
            ),
        )


class ChecklistTemplateItem(BaseModel):
    key: str
    label: str


class InspectionMeta(BaseModel):
    checklist_templates: dict[InstrumentType, list[ChecklistTemplateItem]]
    measurement_labels: dict[InstrumentType, list[str]]
    max_evidence_photos: int

    @classmethod
    def build(cls) -> Self:
        return cls(
            checklist_templates={
                t: [ChecklistTemplateItem(key=i.key, label=i.label) for i in items]
                for t, items in CHECKLIST_TEMPLATES.items()
            },
            measurement_labels={
                t: [measurement_label(f) for f in fractions]
                for t, fractions in MEASUREMENT_TEMPLATES.items()
            },
            max_evidence_photos=MAX_EVIDENCE_PHOTOS,
        )
