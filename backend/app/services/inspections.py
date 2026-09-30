import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.application_types import DocumentType
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.inspection_templates import checklist_summary_counts
from app.models.application import Application
from app.models.document import Document
from app.models.inspection import Inspection
from app.models.inspection_checklist import InspectionChecklistItem, InspectionMeasurement
from app.models.user import User
from app.schemas.document import DocumentOut
from app.schemas.inspection import InspectionDetail, InspectionUpdate
from app.services import audit
from app.services.scoping import scope_inspections


def _now() -> datetime:
    return datetime.now(UTC)


def _checklist_items(db: Session, inspection_id: uuid.UUID) -> list[InspectionChecklistItem]:
    return list(
        db.scalars(
            select(InspectionChecklistItem)
            .where(InspectionChecklistItem.inspection_id == inspection_id)
            .order_by(InspectionChecklistItem.created_at)
        )
    )


def _measurements(db: Session, inspection_id: uuid.UUID) -> list[InspectionMeasurement]:
    return list(
        db.scalars(
            select(InspectionMeasurement)
            .where(InspectionMeasurement.inspection_id == inspection_id)
            .order_by(InspectionMeasurement.created_at)
        )
    )


def _evidence(db: Session, application_id: uuid.UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.application_id == application_id,
                Document.document_type == DocumentType.INSPECTION_EVIDENCE,
            )
            .order_by(Document.created_at)
        )
    )


def get(
    db: Session, user: User, inspection_id: uuid.UUID, *, for_update: bool = False
) -> Inspection:
    """One scoped query: out of scope (incl. wrong org/jurisdiction) is 404, never 403."""
    stmt = (
        scope_inspections(select(Inspection), user)
        .where(Inspection.id == inspection_id)
        .options(joinedload(Inspection.assigned_officer))
    )
    if for_update:
        stmt = stmt.with_for_update(of=Inspection).execution_options(populate_existing=True)
    inspection = db.scalar(stmt)
    if inspection is None:
        raise NotFound("Inspection not found")
    return inspection


def detail(db: Session, user: User, inspection_id: uuid.UUID) -> InspectionDetail:
    inspection = get(db, user, inspection_id)
    return InspectionDetail.build(
        inspection,
        checklist_items=_checklist_items(db, inspection.id),
        measurements=_measurements(db, inspection.id),
        evidence=[DocumentOut.from_model(d) for d in _evidence(db, inspection.application_id)],
        user=user,
    )


def _require_assigned_officer_not_submitted(inspection: Inspection, user: User) -> None:
    if inspection.assigned_officer_id != user.id:
        raise Forbidden("Only the assigned officer can do this")
    if inspection.submitted_at is not None:
        raise Conflict("This inspection has already been submitted")


def patch(
    db: Session, user: User, inspection_id: uuid.UUID, body: InspectionUpdate
) -> InspectionDetail:
    inspection = get(db, user, inspection_id, for_update=True)
    _require_assigned_officer_not_submitted(inspection, user)

    if body.checklist_items:
        by_key = {i.item_key: i for i in _checklist_items(db, inspection.id)}
        for entry in body.checklist_items:
            item = by_key.get(entry.item_key)
            if item is None:
                raise Unprocessable(
                    f"Unknown checklist item: {entry.item_key}", field="checklist_items"
                )
            if entry.result is not None:
                item.result = entry.result
            if entry.remarks is not None:
                item.remarks = entry.remarks

    if body.measurements:
        by_label = {m.label: m for m in _measurements(db, inspection.id)}
        for entry in body.measurements:
            row = by_label.get(entry.label)
            if row is None:
                raise Unprocessable(f"Unknown measurement: {entry.label}", field="measurements")
            if entry.observed_value is not None:
                row.observed_value = entry.observed_value

    if body.overall_remarks is not None:
        inspection.overall_remarks = body.overall_remarks

    db.commit()
    return detail(db, user, inspection_id)


def submit(db: Session, user: User, inspection_id: uuid.UUID, *, ip: str) -> InspectionDetail:
    inspection = get(db, user, inspection_id, for_update=True)
    _require_assigned_officer_not_submitted(inspection, user)

    items = _checklist_items(db, inspection.id)
    measurements = _measurements(db, inspection.id)
    missing_items = [i.item_key for i in items if i.result is None]
    missing_measurements = [m.label for m in measurements if m.observed_value is None]
    if missing_items or missing_measurements:
        parts = []
        if missing_items:
            parts.append(f"checklist items: {', '.join(missing_items)}")
        if missing_measurements:
            parts.append(f"measurements: {', '.join(missing_measurements)}")
        raise Unprocessable(f"Incomplete: {'; '.join(parts)}", field="checklist_items")

    inspection.submitted_at = _now()
    inspection.submitted_by = user.id
    organization_id = db.scalar(
        select(Application.organization_id).where(Application.id == inspection.application_id)
    )
    audit.log(
        db,
        actor=user,
        action="INSPECTION_SUBMITTED",
        entity_type="application",
        entity_id=inspection.application_id,
        organization_id=organization_id,
        details={
            "checklist_summary": checklist_summary_counts(
                i.result.value if i.result else None for i in items
            ),
        },
        ip=ip,
    )
    db.commit()
    return detail(db, user, inspection_id)


def checklist_summary(db: Session, inspection_id: uuid.UUID) -> dict[str, int]:
    items = _checklist_items(db, inspection_id)
    return checklist_summary_counts(i.result.value if i.result else None for i in items)
