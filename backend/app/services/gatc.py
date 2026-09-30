"""GATC eligibility and allocation — spec 15.

Deliberately minimal: this module only resolves *which* GATC organization/user a scheduling
officer may route an inspection to, and answers the narrow "is this GATC caller the one assigned
to this application/inspection" question the router-level dependencies need. It does not
duplicate any inspection/checklist/approve-reject logic — once a GATC user is assigned, they flow
through the exact same services/applications.py: transition() and services/inspections.py
functions an LM_OFFICER already uses.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unprocessable
from app.core.gatc_types import InspectionAssigneeRole
from app.core.roles import OrgType, Role
from app.core.verification_types import VerificationMode
from app.models.application import Application
from app.models.inspection import Inspection
from app.models.organization import Organization
from app.models.user import User
from app.services.scoping import scope_organizations


def list_eligible(db: Session, user: User, category_id: int) -> list[Organization]:
    """GATC organizations, in the caller's own jurisdiction (scope_organizations), whose
    gatc_eligible_category_ids contains category_id. Ordered by name for a stable dropdown."""
    stmt = (
        scope_organizations(select(Organization), user)
        .where(
            Organization.type == OrgType.GATC,
            Organization.gatc_eligible_category_ids.isnot(None),
            Organization.gatc_eligible_category_ids.contains([category_id]),
        )
        .order_by(Organization.name)
    )
    return list(db.scalars(stmt))


def list_org_gatc_users(db: Session, user: User, organization_id: uuid.UUID) -> list[User]:
    """The GATC-role users of one organization, so a scheduling officer can pick a specific
    person (assigned_officer_id's existing "a specific person" semantics, spec 06 D1) rather than
    just an org. Out-of-scope or non-GATC org -> empty list, same "fails closed, never reveals
    existence" posture as every scope_* helper (the router wraps this in a 404 for a genuinely
    unknown/out-of-scope id, matching every other GET-by-id endpoint's convention)."""
    org = db.scalar(
        scope_organizations(select(Organization), user).where(
            Organization.id == organization_id, Organization.type == OrgType.GATC
        )
    )
    if org is None:
        return []
    return list(
        db.scalars(
            select(User)
            .where(
                User.organization_id == organization_id,
                User.role == Role.GATC,
                User.is_active.is_(True),
            )
            .order_by(User.full_name)
        )
    )


def resolve_gatc_assignment(
    db: Session,
    officer: User,
    application: Application,
    gatc_organization_id: uuid.UUID,
    gatc_user_id: uuid.UUID,
) -> User:
    """Validates a GATC routing choice made while scheduling (DOCUMENT_REVIEW -> SCHEDULED) and
    returns the specific GATC User to assign. Two distinct failure shapes, deliberately:

    - 422 (Unprocessable) for a reference that is simply wrong/nonexistent/out of the officer's
      own jurisdiction: an unknown gatc_organization_id, an org that isn't type=GATC, or a
      gatc_user_id that isn't an active GATC-role member of that org. This mirrors this
      codebase's existing "unknown category_id -> 422" (spec 16) / "unknown item_key -> 422"
      (spec 06/11) convention for a mutation whose body names something that doesn't exist.
      Scoping the organization lookup through scope_organizations folds "wrong jurisdiction" into
      this same "doesn't exist as far as you're concerned" 422, rather than a 404/403 — this is a
      request-body validation context, not a resource load, so scope_*'s own 404 convention
      (which is about GET-by-id) doesn't apply verbatim; 422 is this codebase's precedent for a
      bad *reference inside a body* instead.
    - 409 (Conflict) for a reference that is entirely valid on its own, but not allowed for this
      application's current state: the org exists and is GATC, but isn't configured for this
      instrument's category, or the application's verification_mode is ON_SITE (a GATC test
      centre cannot perform an in-situ verification). Mirrors "Document review checklist
      incomplete" / "must be submitted before approving" — legitimate references blocked by a
      business rule, not a bad reference.
    """
    org = db.scalar(
        scope_organizations(select(Organization), officer).where(
            Organization.id == gatc_organization_id
        )
    )
    if org is None or org.type != OrgType.GATC:
        raise Unprocessable("Unknown gatc_organization_id", field="gatc_organization_id")

    category_id = application.instrument.category_id
    eligible_ids = org.gatc_eligible_category_ids or []
    if category_id is None or category_id not in eligible_ids:
        raise Conflict("This GATC organization is not eligible for this instrument's category")
    if application.verification_mode != VerificationMode.OFFICE_TEST_CENTRE:
        raise Conflict("An on-site (in-situ) verification cannot be routed to a GATC test centre")

    gatc_user = db.scalar(
        select(User).where(
            User.id == gatc_user_id,
            User.organization_id == gatc_organization_id,
            User.role == Role.GATC,
            User.is_active.is_(True),
        )
    )
    if gatc_user is None:
        raise Unprocessable("Unknown gatc_user_id", field="gatc_user_id")
    return gatc_user


def is_assigned_gatc_for_application(
    db: Session, *, application_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Router-level check (spec 15): is this GATC user the specific assignee of this
    application's inspection? Used only to let an assigned GATC caller through a router
    dependency that otherwise blanket-rejects role GATC (preserving every pre-existing RBAC
    test's 403 for an unrelated GATC caller, never 404 — see routers/applications.py)."""
    return (
        db.scalar(
            select(Inspection.id).where(
                Inspection.application_id == application_id,
                Inspection.assigned_officer_id == user_id,
                Inspection.assignee_role == InspectionAssigneeRole.GATC,
            )
        )
        is not None
    )


def is_assigned_gatc_for_inspection(
    db: Session, *, inspection_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Same check as is_assigned_gatc_for_application, keyed by inspection id (routers/
    inspections.py, whose path parameter is the inspection, not the application)."""
    return (
        db.scalar(
            select(Inspection.id).where(
                Inspection.id == inspection_id,
                Inspection.assigned_officer_id == user_id,
                Inspection.assignee_role == InspectionAssigneeRole.GATC,
            )
        )
        is not None
    )
