import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.regions import is_valid_region, is_valid_state
from app.core.roles import Role
from app.models.user import User
from app.schemas.common import (
    DistrictCode,
    LowerEmail,
    Name,
    NewPassword,
    StateCode,
    StrictModel,
)


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


class UserListOut(UserOut):
    """Spec 17: GET /api/users listing shape. pending_cases/completed_cases populate only when
    the caller filters role=LM_OFFICER (the LMO directory reuses this same list) — null for every
    other role so the generic Users table never pays for the extra Inspection/Application join."""

    pending_cases: int | None = None
    completed_cases: int | None = None

    @classmethod
    def from_user_with_counts(
        cls, user: User, *, pending: int | None, completed: int | None
    ) -> Self:
        base = UserOut.from_user(user)
        return cls(**base.model_dump(), pending_cases=pending, completed_cases=completed)


class UserActivate(StrictModel):
    """Spec 17 D5: PATCH /api/users/{id} writes exactly this field, nothing else."""

    is_active: bool


class UserCreate(StrictModel):
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
        if not is_valid_state(self.state_code):
            raise ValueError("Unknown state")
        if self.district_code is not None and not is_valid_region(
            self.state_code, self.district_code
        ):
            raise ValueError("Unknown district for this state")
        return self
