import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.roles import Role
from app.models.user import User
from app.schemas.common import DistrictCode, LowerEmail, Name, NewPassword, StateCode


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    organization_id: uuid.UUID | None
    organization_name: str | None
    state_code: str | None
    district_code: str | None
    is_active: bool

    @classmethod
    def from_user(cls, user: User) -> Self:
        org = user.organization
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization_id=user.organization_id,
            organization_name=org.name if org else None,
            # BUSINESS and GATC users inherit jurisdiction from their organization.
            state_code=org.state_code if org else user.state_code,
            district_code=org.district_code if org else user.district_code,
            is_active=user.is_active,
        )


class UserCreate(BaseModel):
    """Official accounts only. BUSINESS uses /auth/register; GATC is deferred."""

    email: LowerEmail
    full_name: Name
    phone: str | None = Field(default=None, max_length=20)
    role: Literal["STATE_ADMIN", "DISTRICT_ADMIN", "LM_OFFICER"]
    password: NewPassword  # MVP: the admin sets the initial password
    state_code: StateCode | None = None
    district_code: DistrictCode | None = None

    @model_validator(mode="after")
    def check_scope(self) -> Self:
        if self.state_code is None:
            raise ValueError(f"state_code is required for {self.role}")
        if self.role == "STATE_ADMIN" and self.district_code is not None:
            raise ValueError("STATE_ADMIN must not have a district_code")
        if self.role != "STATE_ADMIN" and self.district_code is None:
            raise ValueError(f"district_code is required for {self.role}")
        return self
