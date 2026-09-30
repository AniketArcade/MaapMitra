from enum import StrEnum

# Spec 12: a mocked, purely informational payment status. Its own sibling module (mirrors
# core/verification_types.py's own reasoning, spec 14 D3): PaymentStatus needs a *_LABELS dict for
# GET /applications/meta's payment_statuses entry (the frontend must never hardcode it), so it
# doesn't fit the "no labels needed" precedent app/models/certificate.py's own CertificateStatus
# sets (that enum lives on the model directly and has no meta-exposed label dict). It also isn't a
# property of Application itself (unlike verification_mode, a snapshot column on Application) or
# of Instrument, so core/application_types.py / core/instrument_types.py aren't a fit either — it
# belongs to its own new Payment entity.


class PaymentStatus(StrEnum):
    NOT_PAID = "NOT_PAID"
    PENDING = "PENDING"
    PAID = "PAID"


PAYMENT_STATUS_LABELS: dict[PaymentStatus, str] = {
    PaymentStatus.NOT_PAID: "Not paid",
    PaymentStatus.PENDING: "Payment pending",
    PaymentStatus.PAID: "Paid",
}
