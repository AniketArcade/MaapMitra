import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.core.payment_types import PaymentStatus
from app.core.roles import Role
from app.models.application import Application
from app.models.payment import Payment
from app.models.user import User
from app.services import applications as applications_service
from app.services import audit


def _now() -> datetime:
    return datetime.now(UTC)


def mock_pay(db: Session, user: User, application_id: uuid.UUID, *, ip: str) -> Application:
    """Spec 12: a mocked, purely informational payment action. No real payment gateway exists in
    this MVP (root CLAUDE.md's long-open "Payments" decision, now resolved) and — per an explicit
    user decision — this never gates any application status transition; see
    docs/specs/12-payments.md and backend/CLAUDE.md's "Payments (mocked, informational only)"
    subsection for the full reasoning. Scoping/404 is inherited entirely from
    applications_service.load() (out-of-org business -> 404, same as every other endpoint); no
    separate scope_payments() helper exists because a payment is only ever reached through its
    owning application, exactly like scope_certificates()/scope_inspections() reach their rows
    through scope_applications() rather than a bespoke rule of their own.

    Create-vs-upsert: single step, direct to PAID. There is no real gateway to await, so an
    intermediate PENDING row (set, then immediately flipped to PAID in the same request) would add
    a state transition with no observable difference to any caller — simplest thing that works
    for the MVP (root CLAUDE.md's own instruction to Claude).

    Idempotent by construction, not by a pre-check: locking the parent application row before
    looking up (or creating) the Payment row serialises concurrent callers for the same
    application, so two racing mock-pay calls can never both try to INSERT — the second always
    sees the first's already-committed row once it acquires the lock. A call against an
    already-PAID row is a safe no-op: `paid_at` is left exactly as first set (mock-paying again
    isn't a second real payment)."""
    application = applications_service.load(db, user, application_id, for_update=True)
    if user.role != Role.BUSINESS:
        # Router-level `Owner` dependency (require_roles(Role.BUSINESS)) already rejects every
        # other role with 403 before this ever runs. Kept anyway as the same belt-and-suspenders
        # duplicate check every other single-role service action in this codebase keeps (e.g.
        # services/certificates.py: issue()'s own `if user.role != Role.LM_OFFICER` check).
        raise Forbidden("Insufficient permissions")

    payment = db.scalar(select(Payment).where(Payment.application_id == application.id))
    now = _now()
    created = payment is None
    if payment is None:
        payment = Payment(application_id=application.id, status=PaymentStatus.PAID, paid_at=now)
        db.add(payment)
    elif payment.status != PaymentStatus.PAID:
        # Not reachable through this action alone today (mock_pay always writes PAID directly),
        # but handled defensively: a Payment row could exist in a non-PAID state from some other
        # future writer.
        payment.status = PaymentStatus.PAID
        payment.paid_at = now

    audit.log(
        db,
        actor=user,
        action="PAYMENT_MOCKED",
        entity_type="application",
        entity_id=application.id,
        organization_id=application.organization_id,
        details={"status": payment.status.value, "created": created},
        ip=ip,
    )
    db.commit()
    # Keep the already-loaded (lazy="raise") relationship in sync in-memory: `application` was
    # loaded (via _scoped()'s joinedload) before this row existed on a first-ever call, and
    # expire_on_commit=False means it would otherwise never reflect it without a fresh query —
    # same reasoning services/applications.py: transition() documents for its own
    # `application.inspection = inspection` sync.
    application.payment = payment
    return application
