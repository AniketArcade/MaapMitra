import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, joinedload, selectinload

from app.core import clock
from app.core.application_types import (
    DOCUMENT_LABELS,
    REQUIREMENTS,
    ApplicationStatus,
    ApplicationType,
)
from app.core.config import get_settings
from app.core.document_review_templates import DOCUMENT_REVIEW_CHECKLIST_TEMPLATE
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.gatc_types import InspectionAssigneeRole
from app.core.inspection_templates import (
    CHECKLIST_TEMPLATES,
    MEASUREMENT_TEMPLATES,
    measurement_label,
)
from app.core.roles import Role
from app.core.verification_types import verification_mode_for
from app.models.application import (
    ACTIVE_INDEX,
    Application,
    ApplicationStatusHistory,
    application_number_seq,
)
from app.models.document import Document
from app.models.document_review_checklist import DocumentReviewChecklistItem
from app.models.inspection import Inspection
from app.models.inspection_checklist import InspectionChecklistItem, InspectionMeasurement
from app.models.instrument import Instrument
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    InspectionReschedule,
    ReviewChecklistUpdate,
    StatusChange,
)
from app.services import audit
from app.services import gatc as gatc_service
from app.services import inspections as inspections_service
from app.services import instruments as instruments_service
from app.services.scoping import scope_applications
from app.storage import StorageError, get_storage

log = logging.getLogger(__name__)
S = ApplicationStatus


@dataclass(frozen=True)
class Edge:
    roles: frozenset[Role]
    enabled: bool


# The only source of truth for status changes. Later steps flip `enabled`.
ALLOWED_TRANSITIONS: dict[tuple[ApplicationStatus, ApplicationStatus], Edge] = {
    (S.DRAFT, S.SUBMITTED): Edge(frozenset({Role.BUSINESS}), enabled=True),
    (S.SUBMITTED, S.DOCUMENT_REVIEW): Edge(frozenset({Role.LM_OFFICER}), enabled=True),
    (S.DOCUMENT_REVIEW, S.REJECTED): Edge(frozenset({Role.LM_OFFICER}), enabled=True),
    # Step 11: the "fix and resubmit" deficiency loop.
    (S.DOCUMENT_REVIEW, S.DOCUMENTS_DEFICIENT): Edge(frozenset({Role.LM_OFFICER}), enabled=True),
    (S.DOCUMENTS_DEFICIENT, S.SUBMITTED): Edge(frozenset({Role.BUSINESS}), enabled=True),
    (S.DOCUMENT_REVIEW, S.SCHEDULED): Edge(frozenset({Role.LM_OFFICER}), enabled=True),
    # Step 15: GATC added to the three inspection-stage edges below — a GATC-role user reaches
    # them only once assigned (Inspection.assigned_officer_id), scheduling remains LM_OFFICER-only
    # above (a GATC org/user is a *target* of scheduling, never the one who schedules).
    (S.SCHEDULED, S.INSPECTION): Edge(frozenset({Role.LM_OFFICER, Role.GATC}), enabled=True),
    (S.INSPECTION, S.APPROVED): Edge(frozenset({Role.LM_OFFICER, Role.GATC}), enabled=True),
    (S.INSPECTION, S.REJECTED): Edge(frozenset({Role.LM_OFFICER, Role.GATC}), enabled=True),
    # System only: happens inside certificate creation (step 8), never via PATCH.
    (S.APPROVED, S.CERTIFICATE_ISSUED): Edge(frozenset(), enabled=False),
}

REJECT_NOTE_MIN = 10
# Step 11: DOCUMENT_REVIEW -> DOCUMENTS_DEFICIENT requires a note explaining what's missing,
# same length rule as REJECTED's, kept as a sibling constant rather than reused so the two can
# diverge later without an unrelated rename.
DEFICIENCY_NOTE_MIN = 10


def allowed_actions(application: Application, user: User) -> list[ApplicationStatus]:
    """Enabled edges from the current status that the caller's role may take.
    Requirements are not considered (the UI disables Submit until they are met)."""
    actions = [
        to
        for (frm, to), edge in ALLOWED_TRANSITIONS.items()
        if frm == application.status and edge.enabled and user.role in edge.roles
    ]
    if application.status == S.INSPECTION and (
        application.inspection is None or application.inspection.submitted_at is None
    ):
        # Mirrors transition()'s own gate (step 7): Approve/Reject only once the checklist is
        # submitted. Filtered here too so the UI never offers a button that would immediately 409.
        actions = [a for a in actions if a not in (S.APPROVED, S.REJECTED)]
    return actions


def _now() -> datetime:
    return datetime.now(UTC)


def _scoped(user: User) -> Select[tuple[Application]]:
    stmt = select(Application).options(
        joinedload(Application.instrument),
        joinedload(Application.organization),
        joinedload(Application.inspection).joinedload(Inspection.assigned_officer),
        joinedload(Application.certificate),
        joinedload(Application.payment),
    )
    return scope_applications(stmt, user)


def load(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    *,
    for_update: bool = False,
    detail: bool = False,
) -> Application:
    """One scoped query: missing and out-of-scope (incl. DRAFT for officials) are both 404."""
    stmt = _scoped(user).where(Application.id == application_id)
    if detail:
        stmt = stmt.options(
            selectinload(Application.documents),
            selectinload(Application.history).joinedload(ApplicationStatusHistory.actor),
        )
    if for_update:
        stmt = stmt.with_for_update(of=Application).execution_options(populate_existing=True)
    application = db.scalar(stmt)
    if application is None:
        raise NotFound("Application not found")
    return application


def _add_history(
    db: Session,
    application: Application,
    actor: User,
    frm: ApplicationStatus | None,
    to: ApplicationStatus,
    note: str | None = None,
) -> None:
    db.add(
        ApplicationStatusHistory(
            application_id=application.id,
            from_status=frm,
            to_status=to,
            actor_user_id=actor.id,
            note=note,
        )
    )


def create(db: Session, user: User, body: ApplicationCreate, *, ip: str) -> Application:
    # Locks the instrument row: serialises with instrument PATCH (edit lock) and other creates.
    instrument = instruments_service.get(db, user, body.instrument_id, for_update=True)
    seq = db.scalar(select(application_number_seq.next_value()))
    application = Application(
        application_number=f"APP-{_now().year}-{seq:06d}",
        instrument=instrument,
        organization=instrument.organization,
        application_type=body.application_type,
        status=S.DRAFT,
        state_code=instrument.state_code,
        district_code=instrument.district_code,
        # Spec 14: snapshot instrument.transportable -> verification_mode at creation, same
        # timing/reasoning as the state_code/district_code snapshot just above. A later change to
        # the instrument's transportable never retroactively touches this application.
        verification_mode=verification_mode_for(instrument.transportable),
        business_notes=body.business_notes or None,
        created_by=user.id,
        inspection=None,  # a brand-new application never has one; avoids a lazy="raise" trip
    )
    db.add(application)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == ACTIVE_INDEX:
            raise Conflict("This instrument already has an application in progress") from exc
        raise

    _add_history(db, application, user, None, S.DRAFT)
    audit.log(
        db,
        actor=user,
        action="APPLICATION_CREATED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={
            "application_number": application.application_number,
            "instrument_uid": instrument.instrument_uid,
            "application_type": application.application_type.value,
            "verification_mode": application.verification_mode.value,
        },
        ip=ip,
    )
    db.commit()
    return application


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_applications(
    db: Session,
    user: User,
    *,
    q: str | None,
    status: ApplicationStatus | None,
    instrument_id: uuid.UUID | None,
    limit: int,
    offset: int,
    sort: str = "created_desc",
) -> tuple[list[Application], int]:
    # Explicit outerjoin (not joinedload) to Inspection: scheduled_asc needs to ORDER BY a
    # column on it, and SQLAlchemy can't order by a join it added implicitly via joinedload.
    # contains_eager reuses this same join for eager loading, so there's still one join.
    stmt = scope_applications(
        select(Application).join(Application.instrument).outerjoin(Application.inspection),
        user,
    )
    if q:
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            or_(
                Application.application_number.ilike(pattern, escape="\\"),
                Instrument.instrument_uid.ilike(pattern, escape="\\"),
                Instrument.serial_number.ilike(pattern, escape="\\"),
            )
        )
    if status:
        stmt = stmt.where(Application.status == status)
    if instrument_id:
        stmt = stmt.where(Application.instrument_id == instrument_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (
        (Inspection.scheduled_date.asc().nulls_last(), Application.id)
        if sort == "scheduled_asc"
        else (Application.created_at.desc(), Application.id)
    )
    items = db.scalars(
        stmt.options(
            joinedload(Application.instrument),
            joinedload(Application.organization),
            contains_eager(Application.inspection),
        )
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def stats(db: Session, user: User) -> dict[ApplicationStatus, int]:
    """Counts by status, same scoping as list_applications: always consistent with
    what GET /applications?status=... would return for this caller."""
    stmt = scope_applications(
        select(Application.status, func.count()).group_by(Application.status), user
    )
    return dict(db.execute(stmt).all())


def _validate_scheduled_date(d: date | None) -> date:
    """Shared by scheduling and reschedule: today() is in APP_TIMEZONE, not UTC (a UTC-only
    check would reject IST dates for up to 5h30m around midnight)."""
    if d is None:
        raise Unprocessable("A scheduled_date is required", field="scheduled_date")
    lo = clock.today()
    hi = lo + timedelta(days=get_settings().SCHEDULING_MAX_DAYS_AHEAD)
    if not (lo <= d <= hi):
        raise Unprocessable(f"scheduled_date must be between {lo} and {hi}", field="scheduled_date")
    return d


def _require_draft(application: Application, what: str) -> None:
    if application.status != S.DRAFT:
        raise Conflict(f"Only draft applications can be {what}")


def update(
    db: Session, user: User, application_id: uuid.UUID, body: ApplicationUpdate, *, ip: str
) -> Application:
    application = load(db, user, application_id, for_update=True)
    _require_draft(application, "edited")
    sent = body.model_dump(exclude_unset=True)
    if "business_notes" in sent:
        sent["business_notes"] = sent["business_notes"] or None
    changes = {
        field: (getattr(application, field), value)
        for field, value in sent.items()
        if getattr(application, field) != value
    }
    if not changes:
        db.commit()  # releases the lock; nothing written, updated_at unchanged
        return application

    for field, (_, new) in changes.items():
        setattr(application, field, new)
    audit.log(
        db,
        actor=user,
        action="APPLICATION_UPDATED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={
            "changes": {
                f: [
                    o.value if isinstance(o, ApplicationType) else o,
                    n.value if isinstance(n, ApplicationType) else n,
                ]
                for f, (o, n) in changes.items()
            }
        },
        ip=ip,
    )
    db.commit()
    db.refresh(application, ["updated_at"])
    return application


def delete(db: Session, user: User, application_id: uuid.UUID, *, ip: str) -> None:
    application = load(db, user, application_id, for_update=True)
    _require_draft(application, "deleted")
    paths = list(
        db.scalars(select(Document.storage_path).where(Document.application_id == application.id))
    )
    audit.log(
        db,
        actor=user,
        action="APPLICATION_DELETED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={
            "application_number": application.application_number,
            "documents_deleted": len(paths),
        },
        ip=ip,
    )
    db.delete(application)  # documents and history cascade in the database
    db.commit()
    delete_objects_best_effort(paths)


def delete_objects_best_effort(paths: list[str]) -> None:
    if not paths:
        return
    try:
        get_storage().delete(paths)
    except StorageError:
        log.warning("orphaned storage objects left behind: %d", len(paths))


def transition(
    db: Session, user: User, application_id: uuid.UUID, body: StatusChange, *, ip: str
) -> Application:
    """Evaluation order (spec 03 §3): scope 404 → not an edge 409 → role 403 →
    not enabled 409 → edge rules 409/422 → apply."""
    application = load(db, user, application_id, for_update=True)
    current, target = application.status, body.status
    edge = ALLOWED_TRANSITIONS.get((current, target))
    if edge is None:
        raise Conflict("Invalid status change")
    if user.role not in edge.roles:
        raise Forbidden("Insufficient permissions")
    if not edge.enabled:
        raise Conflict("This action is not available yet")
    if target == S.INSPECTION and application.inspection.assigned_officer_id != user.id:
        # Edge(roles, enabled) alone can't express "this specific officer": scope_applications
        # already lets any in-jurisdiction officer read a SCHEDULED application, so this check
        # is load-bearing, not redundant with role/scope (spec 06 §3).
        raise Forbidden("Only the assigned officer can do this")
    if (
        current == S.INSPECTION
        and target in (S.APPROVED, S.REJECTED)
        and application.inspection.submitted_at is None
    ):
        # Approve/Reject is open to any in-scope officer (spec 07 D1, unlike the checklist
        # itself), but only once the checklist is frozen by submission.
        raise Conflict("The inspection checklist must be submitted before approving or rejecting")

    note = body.note or None
    if target == S.REJECTED and (note is None or len(note) < REJECT_NOTE_MIN):
        raise Unprocessable(
            f"A rejection reason of at least {REJECT_NOTE_MIN} characters is required",
            field="note",
        )
    if target == S.DOCUMENTS_DEFICIENT and (note is None or len(note) < DEFICIENCY_NOTE_MIN):
        raise Unprocessable(
            f"A deficiency note of at least {DEFICIENCY_NOTE_MIN} characters is required",
            field="note",
        )
    scheduled_date: date | None = None
    # Step 15: who the Inspection row (created below) will be assigned to. Defaults to
    # self-assigning the scheduling officer — completely unchanged from before this step — unless
    # the request names a GATC organization/user, resolved and validated below.
    assignee_user = user
    assignee_role = InspectionAssigneeRole.LM_OFFICER
    if target == S.SCHEDULED:
        scheduled_date = _validate_scheduled_date(body.scheduled_date)
        # Step 11: can't schedule until the officer has worked through the whole document
        # review checklist, mirroring the "all required documents present" gate on submit below.
        unchecked = list(
            db.scalars(
                select(DocumentReviewChecklistItem.label)
                .where(
                    DocumentReviewChecklistItem.application_id == application.id,
                    DocumentReviewChecklistItem.checked.is_(False),
                )
                .order_by(DocumentReviewChecklistItem.created_at)
            )
        )
        if unchecked:
            raise Conflict(f"Document review checklist incomplete: {', '.join(unchecked)}")
        if body.gatc_organization_id is not None:
            assert body.gatc_user_id is not None  # StatusChange.gatc_pair_valid already enforces
            assignee_user = gatc_service.resolve_gatc_assignment(
                db, user, application, body.gatc_organization_id, body.gatc_user_id
            )
            assignee_role = InspectionAssigneeRole.GATC
    else:
        if body.scheduled_date is not None:
            raise Unprocessable(
                "scheduled_date is only allowed when scheduling an inspection",
                field="scheduled_date",
            )
        if body.gatc_organization_id is not None:
            raise Unprocessable(
                "gatc_organization_id is only allowed when scheduling an inspection",
                field="gatc_organization_id",
            )
    if target == S.SUBMITTED:
        present = set(
            db.scalars(
                select(Document.document_type)
                .where(Document.application_id == application.id)
                .distinct()
            )
        )
        missing = sorted(REQUIREMENTS[application.application_type] - present)
        if missing:
            labels = ", ".join(DOCUMENT_LABELS[m] for m in missing)
            raise Conflict(f"Missing required documents: {labels}")

    application.status = target
    if target == S.SUBMITTED:
        application.submitted_at = _now()
    if scheduled_date:
        history_note = f"Inspection scheduled for {scheduled_date}"
    elif target == S.INSPECTION:
        history_note = "Inspection started"
    else:
        history_note = note
    _add_history(db, application, user, current, target, history_note)
    details: dict[str, object] = {"from": current.value, "to": target.value, "note": note}
    if current == S.INSPECTION and target in (S.APPROVED, S.REJECTED):
        details["checklist_summary"] = inspections_service.checklist_summary(
            db, application.inspection.id
        )
    audit.log(
        db,
        actor=user,
        action="APPLICATION_STATUS_CHANGED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details=details,
        ip=ip,
    )
    if scheduled_date is not None:
        # Lock order: application (already held above), then instrument. A bare row lock, not
        # instruments_service.get(): that function's query joinedloads Instrument.active_application
        # (this same Application row) and, combined with for_update's populate_existing=True,
        # would re-hydrate our just-set, not-yet-flushed application.status from its still-stale
        # DB value — silently reverting the assignment above. This lock has no write of its own;
        # it exists purely to serialise against a concurrent instrument PATCH, so an address
        # change can never land after the instrument becomes SCHEDULED-locked.
        db.execute(
            select(Instrument.id)
            .where(Instrument.id == application.instrument_id)
            .with_for_update()
        ).one()
        inspection = Inspection(
            application_id=application.id,
            scheduled_date=scheduled_date,
            assigned_officer_id=assignee_user.id,
            assignee_role=assignee_role,
        )
        db.add(inspection)
        # Keep the already-loaded (lazy="raise") relationship in sync in-memory: the caller's
        # returned `application` was loaded before this row existed, and expire_on_commit=False
        # means it would otherwise never see it without a fresh query.
        inspection.assigned_officer = assignee_user
        application.inspection = inspection
        audit.log(
            db,
            actor=user,
            action="INSPECTION_SCHEDULED",
            entity_type="application",
            entity_id=application.id,
            organization_id=application.organization_id,
            details={
                "scheduled_date": scheduled_date.isoformat(),
                "assignee_role": assignee_role.value,
                "assigned_officer_id": str(assignee_user.id),
            },
            ip=ip,
        )
    if target == S.DOCUMENT_REVIEW:
        # Step 11: snapshot the document-review checklist. If this application has been through
        # DOCUMENT_REVIEW before (DOCUMENTS_DEFICIENT -> SUBMITTED -> DOCUMENT_REVIEW again), the
        # rows already exist (item_key is unique per application) — reset them to unchecked
        # rather than re-insert, so the officer re-verifies each item against the resubmission
        # instead of inheriting stale answers, while item_key/label stay snapshotted from the
        # first pass (mirrors inspection_checklist_items never changing after the fact).
        existing_review_items = list(
            db.scalars(
                select(DocumentReviewChecklistItem).where(
                    DocumentReviewChecklistItem.application_id == application.id
                )
            )
        )
        if existing_review_items:
            for row in existing_review_items:
                row.checked = False
        else:
            for item in DOCUMENT_REVIEW_CHECKLIST_TEMPLATE:
                db.add(
                    DocumentReviewChecklistItem(
                        application_id=application.id,
                        item_key=item.key,
                        label=item.label,
                    )
                )
        audit.log(
            db,
            actor=user,
            action="DOCUMENT_REVIEW_STARTED",
            entity_type="application",
            entity_id=application.id,
            organization_id=application.organization_id,
            details={
                "checklist_item_count": len(DOCUMENT_REVIEW_CHECKLIST_TEMPLATE),
                "reset": bool(existing_review_items),
            },
            ip=ip,
        )
    if target == S.INSPECTION:
        # Lock order: application (already held above), then instrument — same reasoning as the
        # scheduling branch above (a bare row lock, not instruments_service.get(), to avoid
        # populate_existing re-hydrating the just-mutated Application row from its stale value).
        # Needed here (unlike scheduling) because it reads capacity/capacity_unit/instrument_type,
        # not just to serialise against a concurrent PATCH.
        instrument = db.execute(
            select(Instrument).where(Instrument.id == application.instrument_id).with_for_update()
        ).scalar_one()
        checklist_items = CHECKLIST_TEMPLATES[instrument.instrument_type]
        measurement_fractions = MEASUREMENT_TEMPLATES[instrument.instrument_type]
        for item in checklist_items:
            db.add(
                InspectionChecklistItem(
                    inspection_id=application.inspection.id,
                    item_key=item.key,
                    label=item.label,
                )
            )
        for fraction in measurement_fractions:
            db.add(
                InspectionMeasurement(
                    inspection_id=application.inspection.id,
                    label=measurement_label(fraction),
                    unit=instrument.capacity_unit.value,
                    expected_value=instrument.capacity * Decimal(str(fraction)),
                )
            )
        audit.log(
            db,
            actor=user,
            action="INSPECTION_STARTED",
            entity_type="application",
            entity_id=application.id,
            organization_id=application.organization_id,
            details={
                "checklist_item_count": len(checklist_items),
                "measurement_count": len(measurement_fractions),
            },
            ip=ip,
        )
    db.commit()
    return application


def apply_certificate_issued(db: Session, application: Application, user: User, *, ip: str) -> None:
    """Called only from services/certificates.py, inside its own transaction. The
    APPROVED -> CERTIFICATE_ISSUED edge is system-only (Edge(frozenset(), enabled=False)) and
    never reachable through transition()/PATCH (step 8)."""
    application.status = S.CERTIFICATE_ISSUED
    _add_history(db, application, user, S.APPROVED, S.CERTIFICATE_ISSUED, None)
    audit.log(
        db,
        actor=user,
        action="APPLICATION_STATUS_CHANGED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={"from": "APPROVED", "to": "CERTIFICATE_ISSUED", "note": None},
        ip=ip,
    )


def reschedule(
    db: Session, user: User, application_id: uuid.UUID, body: InspectionReschedule, *, ip: str
) -> Application:
    application = load(db, user, application_id, for_update=True)
    if application.status != S.SCHEDULED:
        raise Conflict("Only a scheduled inspection can be rescheduled")
    new_date = _validate_scheduled_date(body.scheduled_date)
    inspection = application.inspection
    assert inspection is not None  # SCHEDULED implies a row was created when it got there
    if inspection.scheduled_date == new_date:
        db.commit()  # releases the lock; nothing written, updated_at unchanged
        return application

    old_date = inspection.scheduled_date
    inspection.scheduled_date = new_date
    audit.log(
        db,
        actor=user,
        action="INSPECTION_RESCHEDULED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={"changes": {"scheduled_date": [old_date.isoformat(), new_date.isoformat()]}},
        ip=ip,
    )
    db.commit()
    return application


def review_checklist_items(
    db: Session, application_id: uuid.UUID
) -> list[DocumentReviewChecklistItem]:
    """Step 11: the document-review checklist snapshot for an application, in template order."""
    return list(
        db.scalars(
            select(DocumentReviewChecklistItem)
            .where(DocumentReviewChecklistItem.application_id == application_id)
            .order_by(DocumentReviewChecklistItem.created_at)
        )
    )


def patch_review_checklist(
    db: Session,
    user: User,
    application_id: uuid.UUID,
    body: ReviewChecklistUpdate,
    *,
    ip: str,
) -> Application:
    """Step 11: LM_OFFICER toggles individual document-review checklist items, only while the
    application is under DOCUMENT_REVIEW. Mirrors services/inspections.py: patch()'s partial-save
    shape (unknown item_key -> 422, no per-call audit row — same as that endpoint)."""
    application = load(db, user, application_id, for_update=True)
    if application.status != S.DOCUMENT_REVIEW:
        raise Conflict("The review checklist can only be edited during document review")
    by_key = {i.item_key: i for i in review_checklist_items(db, application.id)}
    for entry in body.items:
        item = by_key.get(entry.item_key)
        if item is None:
            raise Unprocessable(f"Unknown checklist item: {entry.item_key}", field="items")
        item.checked = entry.checked
    db.commit()
    return application
