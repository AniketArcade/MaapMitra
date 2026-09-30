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
from app.models.organization import Organization
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
    (a draft is the business's unfinished work; officer queues start at SUBMITTED).
    GATC (spec 15): exactly the application(s) this specific person has been assigned to
    inspect — never a jurisdiction or org-wide view like LM_OFFICER/DISTRICT_ADMIN get. This is
    deliberately narrower than every other official role: a GATC organization may have several
    staff, but only the one individual named in Inspection.assigned_officer_id may see or act on
    that application, mirroring assigned_officer_id's existing "a specific person" semantics
    (spec 06 D1) rather than granting the whole org visibility. A consequence, not a special
    case: "any in-scope GATC user" (the approve/reject wording that already applies to LM_OFFICER)
    necessarily narrows to "the one assigned GATC user" for this role, since scope itself is
    per-assignment. `Application.inspection.has(...)` is a correlated EXISTS, not a join, so it
    never collides with a join some other caller (e.g. list_applications' own explicit
    outerjoin(Application.inspection)) may already have added to the same statement."""
    if user.role == Role.BUSINESS:
        if user.organization_id is None:
            return stmt.where(false())
        return stmt.where(Application.organization_id == user.organization_id)
    if user.role == Role.GATC:
        return stmt.where(Application.inspection.has(Inspection.assigned_officer_id == user.id))

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


def scope_organizations(stmt: Select[Any], user: User) -> Select[Any]:
    """Spec 15: which GATC organizations a scheduling officer may even see/choose from, scoped
    to the caller's own jurisdiction — mirrors scope_instruments' exact state/district rule,
    applied to Organization's own state_code/district_code instead of Instrument's. Used by both
    GET /api/gatc/eligible (the allocation dropdown) and the scheduling-time validation in
    services/gatc.py: resolve_gatc_assignment(), so a caller can never target (or even discover
    the existence of) a GATC organization outside their own jurisdiction.

    BUSINESS/GATC callers never reach this (neither role ever schedules or looks up GATC orgs);
    they fall through to false() like every other unhandled role.
    """
    if user.role == Role.SUPER_ADMIN:
        return stmt
    if user.role == Role.STATE_ADMIN:
        if not user.state_code:
            return stmt.where(false())
        return stmt.where(Organization.state_code == user.state_code)
    if user.role in (Role.DISTRICT_ADMIN, Role.LM_OFFICER):
        if not user.state_code or not user.district_code:
            return stmt.where(false())
        return stmt.where(
            Organization.state_code == user.state_code,
            Organization.district_code == user.district_code,
        )
    return stmt.where(false())
