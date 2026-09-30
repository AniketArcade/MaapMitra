from datetime import date
from typing import Self

from pydantic import BaseModel

from app.core import clock
from app.core.certificate_status import effective_status
from app.core.instrument_types import TYPE_LABELS, InstrumentType
from app.models.certificate import Certificate, CertificateStatus


class PublicVerifyOut(BaseModel):
    """The complete public field set (spec 09 §5), extended by exactly two fields under spec 13's
    explicit authorization (see docs/specs/13-certificate-superseding.md §Decisions) — no owner
    PII, no internal IDs, no document or PDF references. Never add a field here without checking
    spec 09 §5/§10 D4 (and now spec 13) first.

    Step 13 additions:
    - `instrument_uid`: the instrument's own permanent public identifier (spec 02), already shown
      on the certificate PDF anyone with the certificate number can already reach — not owner PII,
      not an internal database id.
    - `issued_by`: a display label for the approving officer, taken from the snapshot's existing
      `approved_by_name` (spec 08's own "issued by" concept — never invented fresh here) rather
      than a raw user id or email.
    Deliberately NOT added: `supersedes`/`superseded_by`/`is_expiring_soon`. A superseded
    certificate's own `status` becoming SUPERSEDED is already the signal a public verifier needs;
    exposing the chain would mean leaking another certificate's internal id, a kind of reference
    this endpoint has never exposed, just to restate what `status` already says. `is_expiring_soon`
    is a VALID-only nuance the reminder job and the business portal already communicate directly
    to the certificate holder — the public page's status values (via `effective_status()`) already
    distinguish VALID/EXPIRED/REVOKED/SUPERSEDED, which is all an outside verifier needs."""

    certificate_number: str
    status: CertificateStatus
    instrument_type_label: str
    instrument_uid: str
    manufacturer: str
    model: str
    serial_number: str
    valid_from: date
    valid_until: date
    issued_by: str

    @classmethod
    def from_model(cls, c: Certificate) -> Self:
        s = c.snapshot
        return cls(
            certificate_number=c.certificate_number,
            status=effective_status(c.status, c.valid_until, today=clock.today()),
            instrument_type_label=TYPE_LABELS[InstrumentType(s["instrument_type"])],
            instrument_uid=s["instrument_uid"],
            manufacturer=s["manufacturer"],
            model=s["model"],
            serial_number=s["serial_number"],
            valid_from=c.valid_from,
            valid_until=c.valid_until,
            issued_by=s.get("approved_by_name") or "",
        )
