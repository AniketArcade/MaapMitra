from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.application_types import TERMINAL_STATUSES
from app.core.config import get_settings
from app.core.regions import REGIONS
from app.models.application import Application
from app.models.certificate import Certificate, CertificateStatus
from app.models.instrument import Instrument
from app.models.user import User
from app.schemas.admin import StateOverviewRow
from app.services.scoping import scope_applications, scope_certificates, scope_instruments

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


def state_overview(db: Session, user: User) -> list[StateOverviewRow]:
    """Spec 17 §6.4: one row per REGIONS state/UT, zero-filled. Reuses scope_instruments/
    scope_applications/scope_certificates unchanged — unfiltered for SUPER_ADMIN (this
    endpoint's only caller today), but a future STATE_ADMIN/DISTRICT_ADMIN caller would
    correctly see every other state's row as zero (spec 17 §5/D1: the data layer already
    generalizes "for free," not built as a UI for those roles yet)."""
    instrument_counts = dict(
        db.execute(
            scope_instruments(
                select(Instrument.state_code, func.count()).group_by(Instrument.state_code), user
            )
        ).all()
    )
    pending_counts = dict(
        db.execute(
            scope_applications(
                select(Application.state_code, func.count())
                .where(Application.status.notin_(TERMINAL_STATUSES))
                .group_by(Application.state_code),
                user,
            )
        ).all()
    )
    # scope_certificates() already joins Certificate -> Application internally — do not join it
    # again here, or SQLAlchemy ends up with the same table joined twice.
    cert_rows = db.execute(
        scope_certificates(
            select(
                Application.state_code,
                func.count().filter(Certificate.status == S.VALID),
                func.count().filter(Certificate.status == S.EXPIRED),
            )
            .select_from(Certificate)
            .group_by(Application.state_code),
            user,
        )
    ).all()
    certs_valid = {code: valid for code, valid, _ in cert_rows}
    certs_expired = {code: expired for code, _, expired in cert_rows}

    return [
        StateOverviewRow(
            state_code=code,
            state_name=REGIONS[code]["name"],
            instrument_count=instrument_counts.get(code, 0),
            pending_applications=pending_counts.get(code, 0),
            certs_valid=certs_valid.get(code, 0),
            certs_expired=certs_expired.get(code, 0),
        )
        for code in REGIONS
    ]
