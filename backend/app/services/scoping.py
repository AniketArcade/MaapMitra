"""Row-level scoping for org-owned data. Every read of business data goes through here.

Out of scope means "not found" (404), never 403, so callers can't probe for existence.
Fails closed: an unknown role or an official missing required codes sees nothing.
"""

from typing import Any

from sqlalchemy import Select, false

from app.core.roles import Role
from app.models.instrument import Instrument
from app.models.user import User


def scope_instruments(stmt: Select[Any], user: User) -> Select[Any]:
    if user.role == Role.BUSINESS:
        if user.organization_id is None:
            return stmt.where(false())
        return stmt.where(Instrument.organization_id == user.organization_id)
    if user.role == Role.SUPER_ADMIN:
        return stmt
    if user.role == Role.STATE_ADMIN:
        if not user.state_code:
            return stmt.where(false())
        return stmt.where(Instrument.state_code == user.state_code)
    if user.role in (Role.DISTRICT_ADMIN, Role.LM_OFFICER):
        if not user.state_code or not user.district_code:
            return stmt.where(false())
        return stmt.where(
            Instrument.state_code == user.state_code,
            Instrument.district_code == user.district_code,
        )
    return stmt.where(false())
