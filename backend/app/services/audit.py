import uuid
from typing import Any

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
