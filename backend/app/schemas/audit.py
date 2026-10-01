import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel

from app.models.audit_log import AuditLog


class AuditLogOut(BaseModel):
    """Spec 17: GET /api/audit-logs. actor_name is resolved via an outer join to users (not a
    nested ref — this is a flat read, same convention CertificateOut/ApplicationOut already use);
    null means the system itself acted (e.g. the expiry job, step 10), not an unknown user —
    frontend renders "System" for a null actor_name."""

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    details: dict[str, Any]
    ip_address: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: AuditLog, actor_name: str | None) -> Self:
        return cls(
            id=row.id,
            actor_user_id=row.actor_user_id,
            actor_name=actor_name,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            organization_id=row.organization_id,
            details=row.details,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
