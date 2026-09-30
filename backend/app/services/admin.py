from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.certificate import Certificate, CertificateStatus
from app.models.user import User
from app.services.scoping import scope_certificates

S = CertificateStatus


def certificate_stats(db: Session, user: User) -> tuple[dict[CertificateStatus, int], int]:
    """Same scoping as expiring_soon(): a SUPER_ADMIN's counts always match what the
    expiring-soon list would return for them, a STATE_ADMIN/DISTRICT_ADMIN's counts stay
    within their own jurisdiction."""
    by_status = dict(
        db.execute(
            scope_certificates(
                select(Certificate.status, func.count()).group_by(Certificate.status), user
            )
        ).all()
    )
    horizon = clock.today() + timedelta(days=get_settings().EXPIRY_REMINDER_30D_DAYS)
    expiring_soon = db.scalar(
        scope_certificates(select(func.count()).select_from(Certificate), user).where(
            Certificate.status == S.VALID, Certificate.valid_until <= horizon
        )
    )
    return by_status, expiring_soon or 0


def expiring_soon(
    db: Session, user: User, *, limit: int, offset: int
) -> tuple[list[Certificate], int]:
    horizon = clock.today() + timedelta(days=get_settings().EXPIRY_REMINDER_30D_DAYS)
    stmt = scope_certificates(select(Certificate), user).where(
        Certificate.status == S.VALID, Certificate.valid_until <= horizon
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(stmt.order_by(Certificate.valid_until.asc()).limit(limit).offset(offset))
    )
    return items, total
