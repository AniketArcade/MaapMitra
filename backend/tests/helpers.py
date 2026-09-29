from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import AuditLog, RefreshToken


def audit_rows(action: str) -> list[AuditLog]:
    """Read in a fresh session, so we only see committed rows."""
    with SessionLocal() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)))


def active_refresh_tokens(user_id) -> int:  # noqa: ANN001
    with SessionLocal() as s:
        return s.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )


def set_cookie_headers(response) -> list[str]:  # noqa: ANN001
    return response.headers.get_list("set-cookie")


def cleared(response, name: str) -> bool:  # noqa: ANN001
    return any(h.startswith(f"{name}=") and "Max-Age=0" in h for h in set_cookie_headers(response))
