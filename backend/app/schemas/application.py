import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, model_validator

from app.core.application_types import (
    ALLOWED_CONTENT_TYPES,
    APPLICATION_TYPE_LABELS,
    BUSINESS_DOCUMENT_TYPES,
    DOCUMENT_LABELS,
    MAX_DOCUMENTS,
    MAX_FILE_BYTES,
    REQUIREMENTS,
    STATUS_LABELS,
    ApplicationStatus,
    ApplicationType,
    DocumentType,
)
from app.core.config import get_settings
from app.core.instrument_types import CapacityUnit, InstrumentType
from app.core.roles import Role
from app.models.application import Application
from app.models.user import User
from app.schemas.common import StrictModel
from app.schemas.document import DocumentOut

Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ApplicationCreate(StrictModel):
    instrument_id: uuid.UUID
    application_type: ApplicationType
    business_notes: Notes | None = None


class ApplicationUpdate(StrictModel):
    """DRAFT only. business_notes may be cleared with null; application_type may not."""

    application_type: ApplicationType | None = None
    business_notes: Notes | None = None

    @model_validator(mode="after")
    def type_not_null(self) -> Self:
        if "application_type" in self.model_fields_set and self.application_type is None:
            raise ValueError("application_type cannot be null")
        return self


class StatusChange(StrictModel):
    status: ApplicationStatus
    note: Notes | None = None
    scheduled_date: date | None = None  # required for, and only for, target SCHEDULED


class InspectionReschedule(StrictModel):
    scheduled_date: date


class InstrumentSummary(BaseModel):
    id: uuid.UUID
    instrument_uid: str
    instrument_type: InstrumentType
    manufacturer: str
    model: str
    serial_number: str
    capacity: float
    capacity_unit: CapacityUnit


class ApplicationOut(BaseModel):
    id: uuid.UUID
    application_number: str
    status: ApplicationStatus
    application_type: ApplicationType
    instrument: InstrumentSummary
    organization_id: uuid.UUID
    organization_name: str
    state_code: str
    district_code: str
    business_notes: str | None
    submitted_at: datetime | None
    scheduled_date: date | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, a: Application) -> Self:
        i = a.instrument
        return cls(
            id=a.id,
            application_number=a.application_number,
            status=a.status,
            application_type=a.application_type,
            instrument=InstrumentSummary(
                id=i.id,
                instrument_uid=i.instrument_uid,
                instrument_type=i.instrument_type,
                manufacturer=i.manufacturer,
                model=i.model,
                serial_number=i.serial_number,
                capacity=float(i.capacity),
                capacity_unit=i.capacity_unit,
            ),
            organization_id=a.organization_id,
            organization_name=a.organization.name,
            state_code=a.state_code,
            district_code=a.district_code,
            business_notes=a.business_notes,
            submitted_at=a.submitted_at,
            scheduled_date=a.inspection.scheduled_date if a.inspection else None,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )


class HistoryOut(BaseModel):
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    actor_name: str
    note: str | None
    created_at: datetime


class RequirementOut(BaseModel):
    document_type: DocumentType
    label: str
    required: bool
    satisfied: bool


class ChecklistSummary(BaseModel):
    passed: int
    failed: int
    na: int


class InspectionOut(BaseModel):
    id: uuid.UUID
    scheduled_date: date
    assigned_officer_name: str
    submitted_at: datetime | None
    checklist_summary: ChecklistSummary | None


class ApplicationDetail(ApplicationOut):
    documents: list[DocumentOut]
    history: list[HistoryOut]
    requirements: list[RequirementOut]
    allowed_actions: list[ApplicationStatus]
    inspection: InspectionOut | None
    can_reschedule: bool

    @classmethod
    def build(
        cls,
        a: Application,
        user: User,
        allowed_actions: list[ApplicationStatus],
        *,
        checklist_summary: dict[str, int] | None = None,
    ) -> Self:
        present = {d.document_type for d in a.documents}
        required = REQUIREMENTS[a.application_type]
        return cls(
            **ApplicationOut.from_model(a).model_dump(),
            documents=[DocumentOut.from_model(d) for d in a.documents],
            history=[
                HistoryOut(
                    from_status=h.from_status,
                    to_status=h.to_status,
                    actor_name=h.actor.full_name,
                    note=h.note,
                    created_at=h.created_at,
                )
                for h in a.history
            ],
            requirements=[
                RequirementOut(
                    document_type=t,
                    label=DOCUMENT_LABELS[t],
                    required=t in required,
                    satisfied=t in present,
                )
                for t in BUSINESS_DOCUMENT_TYPES
            ],
            allowed_actions=allowed_actions,
            inspection=(
                InspectionOut(
                    id=a.inspection.id,
                    scheduled_date=a.inspection.scheduled_date,
                    assigned_officer_name=a.inspection.assigned_officer.full_name,
                    submitted_at=a.inspection.submitted_at,
                    checklist_summary=(
                        ChecklistSummary(
                            passed=checklist_summary["PASS"],
                            failed=checklist_summary["FAIL"],
                            na=checklist_summary["NA"],
                        )
                        if checklist_summary
                        else None
                    ),
                )
                if a.inspection
                else None
            ),
            # Scope already implies jurisdiction: reaching this point means the caller may read it.
            can_reschedule=(
                a.status == ApplicationStatus.SCHEDULED and user.role == Role.LM_OFFICER
            ),
        )


class ApplicationStats(BaseModel):
    total: int
    by_status: dict[ApplicationStatus, int]

    @classmethod
    def from_counts(cls, counts: dict[ApplicationStatus, int]) -> Self:
        by_status = {s: counts.get(s, 0) for s in ApplicationStatus}
        return cls(total=sum(by_status.values()), by_status=by_status)


class LabelledValue(BaseModel):
    value: str
    label: str


class ApplicationTypeMeta(LabelledValue):
    required_documents: list[DocumentType]


class UploadLimits(BaseModel):
    max_file_bytes: int
    max_documents: int
    allowed_content_types: list[str]


class SchedulingMeta(BaseModel):
    timezone: str
    max_days_ahead: int


class ApplicationMeta(BaseModel):
    application_types: list[ApplicationTypeMeta]
    statuses: list[LabelledValue]
    document_types: list[LabelledValue]
    limits: UploadLimits
    scheduling: SchedulingMeta

    @classmethod
    def build(cls) -> Self:
        settings = get_settings()
        return cls(
            scheduling=SchedulingMeta(
                timezone=settings.APP_TIMEZONE,
                max_days_ahead=settings.SCHEDULING_MAX_DAYS_AHEAD,
            ),
            application_types=[
                ApplicationTypeMeta(
                    value=t,
                    label=APPLICATION_TYPE_LABELS[t],
                    required_documents=[d for d in BUSINESS_DOCUMENT_TYPES if d in REQUIREMENTS[t]],
                )
                for t in ApplicationType
            ],
            statuses=[LabelledValue(value=s, label=STATUS_LABELS[s]) for s in ApplicationStatus],
            document_types=[
                LabelledValue(value=d, label=DOCUMENT_LABELS[d]) for d in BUSINESS_DOCUMENT_TYPES
            ],
            limits=UploadLimits(
                max_file_bytes=MAX_FILE_BYTES,
                max_documents=MAX_DOCUMENTS,
                allowed_content_types=list(ALLOWED_CONTENT_TYPES),
            ),
        )
