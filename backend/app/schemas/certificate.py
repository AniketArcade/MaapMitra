import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.instrument_types import CapacityUnit, InstrumentType
from app.models.certificate import Certificate, CertificateStatus
from app.pdf.certificate import qr_code_data_uri


class CertificateOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    certificate_number: str
    status: CertificateStatus
    valid_from: date
    valid_until: date
    issued_at: datetime
    instrument_uid: str
    instrument_type: InstrumentType
    manufacturer: str
    model: str
    serial_number: str
    capacity: float
    capacity_unit: CapacityUnit
    organization_name: str
    qr_code_data_uri: str  # "data:image/png;base64,...", regenerated on every read — never stored

    @classmethod
    def from_model(cls, c: Certificate) -> Self:
        s = c.snapshot
        verify_url = f"{get_settings().PUBLIC_BASE_URL}/verify/{c.certificate_number}"
        return cls(
            id=c.id,
            application_id=c.application_id,
            certificate_number=c.certificate_number,
            status=c.status,
            valid_from=c.valid_from,
            valid_until=c.valid_until,
            issued_at=c.created_at,
            instrument_uid=s["instrument_uid"],
            instrument_type=s["instrument_type"],
            manufacturer=s["manufacturer"],
            model=s["model"],
            serial_number=s["serial_number"],
            capacity=s["capacity"],
            capacity_unit=s["capacity_unit"],
            organization_name=s["organization_name"],
            qr_code_data_uri=qr_code_data_uri(verify_url),
        )


class CertificateUrl(BaseModel):
    url: str
    expires_in: int
