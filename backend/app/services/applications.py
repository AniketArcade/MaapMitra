import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.application_types import (
    DOCUMENT_LABELS,
    REQUIREMENTS,
    ApplicationStatus,
    ApplicationType,
)
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.roles import Role
from app.models.application import (
    ACTIVE_INDEX,
    Application,
    ApplicationStatusHistory,
    application_number_seq,
)
from app.models.document import Document
from app.models.instrument import Instrument
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationUpdate, StatusChange
from app.services import audit
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
    (S.DOCUMENT_REVIEW, S.SCHEDULED): Edge(frozenset({Role.LM_OFFICER}), enabled=False),  # step 5
    (S.SCHEDULED, S.INSPECTION): Edge(frozenset({Role.LM_OFFICER}), enabled=False),  # step 6
    (S.INSPECTION, S.APPROVED): Edge(frozenset({Role.LM_OFFICER}), enabled=False),  # step 7
    (S.INSPECTION, S.REJECTED): Edge(frozenset({Role.LM_OFFICER}), enabled=False),  # step 7
    # System only: happens inside certificate creation (step 8), never via PATCH.
    (S.APPROVED, S.CERTIFICATE_ISSUED): Edge(frozenset(), enabled=False),
}

REJECT_NOTE_MIN = 10


def allowed_actions(application: Application, user: User) -> list[ApplicationStatus]:
    """Enabled edges from the current status that the caller's role may take.
    Requirements are not considered (the UI disables Submit until they are met)."""
    return [
        to
        for (frm, to), edge in ALLOWED_TRANSITIONS.items()
        if frm == application.status and edge.enabled and user.role in edge.roles
    ]


def _now() -> datetime:
    return datetime.now(UTC)


def _scoped(user: User) -> Select[tuple[Application]]:
    stmt = select(Application).options(
        joinedload(Application.instrument), joinedload(Application.organization)
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
        business_notes=body.business_notes or None,
        created_by=user.id,
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
) -> tuple[list[Application], int]:
    stmt = scope_applications(select(Application).join(Application.instrument), user)
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
    items = db.scalars(
        stmt.options(joinedload(Application.instrument), joinedload(Application.organization))
        .order_by(Application.created_at.desc(), Application.id)
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

    note = body.note or None
    if target == S.REJECTED and (note is None or len(note) < REJECT_NOTE_MIN):
        raise Unprocessable(
            f"A rejection reason of at least {REJECT_NOTE_MIN} characters is required",
            field="note",
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
    _add_history(db, application, user, current, target, note)
    audit.log(
        db,
        actor=user,
        action="APPLICATION_STATUS_CHANGED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={"from": current.value, "to": target.value, "note": note},
        ip=ip,
    )
    db.commit()
    return application
