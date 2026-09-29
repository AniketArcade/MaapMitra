from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
)


def _upper(v: object) -> object:
    return v.strip().upper() if isinstance(v, str) else v


LowerEmail = Annotated[EmailStr, AfterValidator(lambda v: v.lower())]
NewPassword = Annotated[SecretStr, Field(min_length=8, max_length=128)]
StateCode = Annotated[str, BeforeValidator(_upper), StringConstraints(pattern=r"^[A-Z]{2}$")]
DistrictCode = Annotated[str, BeforeValidator(_upper), StringConstraints(pattern=r"^[A-Z]{2,4}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StrictModel(BaseModel):
    """Base for every request body: unknown fields are rejected with 422."""

    model_config = ConfigDict(extra="forbid")
