import uuid
from typing import Self

from pydantic import BaseModel

from app.models.user import User


class GatcDirectoryUserOut(BaseModel):
    """One GATC-role user of a directory org — Activate/Deactivate targets this id (via the
    existing PATCH /api/users/{id}), never the organization itself: Organization has no
    is_active column of its own (see GatcDirectoryOut.active below)."""

    id: uuid.UUID
    full_name: str
    email: str
    is_active: bool

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(id=user.id, full_name=user.full_name, email=user.email, is_active=user.is_active)


class GatcDirectoryOut(BaseModel):
    """Spec 17 §6.5/D3: a purpose-built directory, separate from GET /api/gatc/eligible (which
    stays the scheduling officer's category-filtered allocation dropdown)."""

    id: uuid.UUID
    name: str
    state_code: str
    district_code: str
    eligible_categories: list[str]  # resolved names, never raw instrument_categories ids
    pending_cases: int
    completed_cases: int
    active: bool  # True iff >=1 active GATC-role user belongs to this org
    users: list[GatcDirectoryUserOut]
