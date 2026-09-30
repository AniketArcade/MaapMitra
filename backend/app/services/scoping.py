"""Row-level scoping for org-owned data. Every read of business data goes through here.

Out of scope means "not found" (404), never 403, so callers can't probe for existence.
Fails closed: an unknown role or an official missing required codes sees nothing.
"""

from typing import Any

from sqlalchemy import Select, false

from app.core.application_types import ApplicationStatus
from app.core.roles import Role
from app.models.application import Application
from app.models.certificate import Certificate
from app.models.document import Document
from app.models.inspection import Inspection
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


def scope_applications(stmt: Select[Any], user: User) -> Select[Any]:
    """Business: own org, every status. Officials: jurisdiction, and never DRAFT
    (a draft is the business's unfinished work; officer queues start at SUBMITTED)."""
    if user.role == Role.BUSINESS:
        if user.organization_id is None:
            return stmt.where(false())
        return stmt.where(Application.organization_id == user.organization_id)

    not_draft = Application.status != ApplicationStatus.DRAFT
    if user.role == Role.SUPER_ADMIN:
        return stmt.where(not_draft)
    if user.role == Role.STATE_ADMIN:
        if not user.state_code:
            return stmt.where(false())
        return stmt.where(not_draft, Application.state_code == user.state_code)
    if user.role in (Role.DISTRICT_ADMIN, Role.LM_OFFICER):
        if not user.state_code or not user.district_code:
            return stmt.where(false())
        return stmt.where(
            not_draft,
            Application.state_code == user.state_code,
            Application.district_code == user.district_code,
        )
    return stmt.where(false())


def scope_documents(stmt: Select[Any], user: User) -> Select[Any]:
    """Documents are only ever reached through their application's scope."""
    return scope_applications(
        stmt.join(Application, Document.application_id == Application.id), user
    )


def scope_inspections(stmt: Select[Any], user: User) -> Select[Any]:
    """An inspection is only ever reached through its application's scope (step 6)."""
    return scope_applications(
        stmt.join(Application, Inspection.application_id == Application.id), user
    )


def scope_certificates(stmt: Select[Any], user: User) -> Select[Any]:
    """A certificate is only ever reached through its application's scope (step 8)."""
    return scope_applications(
        stmt.join(Application, Certificate.application_id == Application.id), user
    )
