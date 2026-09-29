from typing import Annotated

from fastapi import Query
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


def _collapse(v: object) -> object:
    return " ".join(v.split()) if isinstance(v, str) else v


def _serial(v: object) -> object:
    return v.strip().upper() if isinstance(v, str) else v


# Trimmed, internal whitespace collapsed ("Essae  Teraoka" == "Essae Teraoka").
Text100 = Annotated[
    str, BeforeValidator(_collapse), StringConstraints(min_length=1, max_length=100)
]
Text500 = Annotated[
    str, BeforeValidator(_collapse), StringConstraints(min_length=1, max_length=500)
]
# Trimmed and uppercased; internal whitespace is rejected by the pattern.
Serial = Annotated[
    str,
    BeforeValidator(_serial),
    StringConstraints(min_length=1, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9\-/._]*$"),
]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams:
    """Query-string paging, used as `Annotated[PageParams, Depends()]`."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
