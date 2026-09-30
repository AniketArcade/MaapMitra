import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.payment_types import PaymentStatus
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk


class Payment(UUIDPk, Timestamps, Base):
    """Spec 12: one mocked, purely informational payment record per application. Unlike
    Certificate/Inspection (created by the lifecycle itself, the instant an application reaches a
    given status), a Payment row is created lazily — only when POST /applications/{id}/mock-pay is
    first called — so most applications never get one at all; ApplicationDetail.payment is `null`
    until then, not a zero-value row. Deliberately NOT wired into
    services/applications.py: ALLOWED_TRANSITIONS/transition() in any way: this table is
    informational only, per an explicit user decision recorded in backend/CLAUDE.md's resolved
    "Payments" open-decision bullet and docs/specs/12-payments.md. `ON DELETE CASCADE`: an
    application can still be deleted while DRAFT (services/applications.py: delete()), and a mocked
    payment row has no independent reason to survive its own application, unlike a certificate
    (`RESTRICT`, since a certificate is never issued for anything but a terminal, undeletable
    application)."""

    __tablename__ = "payments"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Nullable: no real payment gateway or fee schedule exists in this MVP (ASSUMPTION — the same
    # long-open "Payments: mocked in MVP" line in ../CLAUDE.md this spec resolves). mock_pay()
    # never sets it; it exists so a real integration can populate it later without a schema change.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        nullable=False,
        server_default=PaymentStatus.NOT_PAID.value,
    )
    # Set only once services/payments.py: mock_pay() flips status to PAID. NULL means "never paid
    # (mocked or otherwise)".
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
