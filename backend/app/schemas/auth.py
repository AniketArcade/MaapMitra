from typing import Literal, Self

from pydantic import BaseModel, Field, SecretStr, model_validator

from app.core.regions import is_valid_region
from app.schemas.common import (
    DistrictCode,
    LowerEmail,
    Name,
    NewPassword,
    StateCode,
    StrictModel,
)
from app.schemas.user import UserOut


class RegisterRequest(StrictModel):  # a client-sent "role" -> 422
    organization_name: Name = Field(min_length=2)
    registration_number: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    state_code: StateCode
    district_code: DistrictCode
    full_name: Name
    email: LowerEmail
    phone: str | None = Field(default=None, max_length=20)
    password: NewPassword

    @model_validator(mode="after")
    def check_region(self) -> Self:
        if not is_valid_region(self.state_code, self.district_code):
            raise ValueError("Unknown state or district")
        return self


class LoginRequest(StrictModel):
    email: LowerEmail
    password: SecretStr = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut
