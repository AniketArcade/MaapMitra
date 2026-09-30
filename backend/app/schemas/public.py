from datetime import date
from typing import Self

from pydantic import BaseModel

from app.core import clock
from app.core.certificate_status import effective_status
from app.core.instrument_types import TYPE_LABELS, InstrumentType
from app.models.certificate import Certificate, CertificateStatus


class PublicVerifyOut(BaseModel):
    """The complete public field set (spec 09 §5) — no owner PII, no internal IDs, no document or
    PDF references. Never add a field here without checking spec 09 §5/§10 D4 first."""

    certificate_number: str
    status: CertificateStatus
    instrument_type_label: str
    manufacturer: str
    model: str
    serial_number: str
    valid_from: date
    valid_until: date

    @classmethod
    def from_model(cls, c: Certificate) -> Self:
        s = c.snapshot
        return cls(
            certificate_number=c.certificate_number,
            status=effective_status(c.status, c.valid_until, today=clock.today()),
            instrument_type_label=TYPE_LABELS[InstrumentType(s["instrument_type"])],
            manufacturer=s["manufacturer"],
            model=s["model"],
            serial_number=s["serial_number"],
            valid_from=c.valid_from,
            valid_until=c.valid_until,
        )
