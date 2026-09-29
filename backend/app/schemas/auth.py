from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.common import DistrictCode, LowerEmail, Name, NewPassword, StateCode
from app.schemas.user import UserOut


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # a client-sent "role" is silently dropped

    organization_name: Name = Field(min_length=2)
    registration_number: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    state_code: StateCode
    district_code: DistrictCode
    full_name: Name
    email: LowerEmail
    phone: str | None = Field(default=None, max_length=20)
    password: NewPassword


class LoginRequest(BaseModel):
    email: LowerEmail
    password: SecretStr = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut
