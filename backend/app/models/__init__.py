# Import every model module here so Alembic autogenerate sees it.
from app.models.application import Application, ApplicationStatusHistory
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.inspection import Inspection
from app.models.instrument import Instrument
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationStatusHistory",
    "AuditLog",
    "Document",
    "Inspection",
    "Instrument",
    "Organization",
    "RefreshToken",
    "User",
]
