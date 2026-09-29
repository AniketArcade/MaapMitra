import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log(
    db: Session,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Add an audit row to the caller's transaction. Never pass passwords or tokens."""
    db.add(
        AuditLog(
            action=action,
            actor_user_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=org_id,
            details=details or {},
            ip_address=ip,
        )
    )
