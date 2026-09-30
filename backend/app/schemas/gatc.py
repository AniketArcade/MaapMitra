import uuid
from typing import Self

from pydantic import BaseModel

from app.models.organization import Organization
from app.models.user import User


class GatcEligibleOrgOut(BaseModel):
    """One row for a scheduling officer's allocation dropdown (spec 15). Deliberately thin: an
    id to submit back on PATCH .../status, plus enough to render the dropdown (name, district/
    state) — no address, no registration_number, no eligible-category list (the caller already
    knows the category_id it queried for)."""

    id: uuid.UUID
    name: str
    state_code: str
    district_code: str

    @classmethod
    def from_model(cls, o: Organization) -> Self:
        return cls(id=o.id, name=o.name, state_code=o.state_code, district_code=o.district_code)


class GatcOrgUserOut(BaseModel):
    """One GATC-role user of an organization, for picking the specific gatc_user_id to submit
    alongside gatc_organization_id (spec 15 — assignment targets a person, not just an org)."""

    id: uuid.UUID
    full_name: str
    email: str

    @classmethod
    def from_model(cls, u: User) -> Self:
        return cls(id=u.id, full_name=u.full_name, email=u.email)
