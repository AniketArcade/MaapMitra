from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel

from app.core.payment_types import PaymentStatus
from app.models.payment import Payment


class PaymentOut(BaseModel):
    """Spec 12: nested on ApplicationDetail.payment only (no dedicated GET endpoint exists, or is
    needed — a payment is only ever read alongside its application). No id/application_id: unlike
    CertificateOut/InspectionOut (each independently fetchable via their own GET .../{id}), this
    schema has nothing to flatly reference against."""

    status: PaymentStatus
    amount: Decimal | None
    paid_at: datetime | None

    @classmethod
    def from_model(cls, p: Payment) -> Self:
        return cls(status=p.status, amount=p.amount, paid_at=p.paid_at)
