import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def log(
    db: Session,
    *,
    actor: User | uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Add an audit row to the caller's transaction. Never pass passwords or tokens."""
    actor_id = actor.id if isinstance(actor, User) else actor
    db.add(
        AuditLog(
            action=action,
            actor_user_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=organization_id,
            details=details or {},
            ip_address=ip,
        )
    )


def list_audit_logs(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    actor_user_id: uuid.UUID | None,
    action: str | None,
    entity_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[AuditLog, str | None]], int]:
    """Spec 17: read side of the audit log, alongside log() above. Returns (row, actor_name)
    pairs — actor_name is None both for a system actor (actor_user_id IS NULL) and, harmlessly,
    for a since-deleted user (no delete path exists today, but the outer join degrades safely)."""
    stmt = select(AuditLog, User.full_name).outerjoin(User, AuditLog.actor_user_id == User.id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        # Inclusive of the whole end day: created_at is a timestamptz, date_to is a bare date.
        stmt = stmt.where(AuditLog.created_at < date_to + timedelta(days=1))
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
    ).all()
    return [(row.AuditLog, row.full_name) for row in rows], total
