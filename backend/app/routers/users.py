import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.deps import DB, get_client_ip, require_roles
from app.core.roles import ADMIN_ROLES, Role
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.user import UserActivate, UserCreate, UserListOut, UserOut
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

# Spec 18 §4: widened from SUPER_ADMIN-only. Unlike organizations, `users` has no scope_* floor
# of its own, so list_users()/create_user()/set_active() each do their own actor-aware narrowing
# for a STATE_ADMIN caller (see services/users.py) — the role Literal below still admits
# "STATE_ADMIN"/"SUPER_ADMIN" because a SUPER_ADMIN caller still needs them.
# Spec 21 D1: DISTRICT_ADMIN is deliberately NOT added here — the source brief for that role never
# lists an account-creation action, only view/activate-deactivate (see Admin below).
SuperOrStateAdmin = Annotated[User, Depends(require_roles(Role.SUPER_ADMIN, Role.STATE_ADMIN))]
# Spec 21 §4: GET/PATCH widened to admit DISTRICT_ADMIN too — list_users()/set_active() each gain
# a DISTRICT_ADMIN branch (state AND district forced, role narrowed to LM_OFFICER only).
Admin = Annotated[User, Depends(require_roles(*ADMIN_ROLES))]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(request: Request, body: UserCreate, actor: SuperOrStateAdmin, db: DB) -> UserOut:
    user = users_service.create_user(db, actor, body, ip=get_client_ip(request))
    return UserOut.from_user(user)


# Spec 17: official-account directory (never BUSINESS/GATC — see OFFICIAL_ROLES).
@router.get("")
def list_users(
    actor: Admin,
    db: DB,
    paging: Annotated[PageParams, Depends()],
    role: Annotated[
        Literal["SUPER_ADMIN", "STATE_ADMIN", "DISTRICT_ADMIN", "LM_OFFICER"] | None, Query()
    ] = None,
    state_code: Annotated[str | None, Query(max_length=2)] = None,
    district_code: Annotated[str | None, Query(max_length=4)] = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[UserListOut]:
    items, counts, total = users_service.list_users(
        db,
        actor,
        role=Role(role) if role else None,
        state_code=state_code,
        district_code=district_code,
        is_active=is_active,
        q=q.strip() if q else None,
        limit=paging.page_size,
        offset=paging.offset,
    )
    return Page(
        items=[
            UserListOut.from_user_with_counts(
                u,
                pending=counts.get(u.id, (None, None))[0],
                completed=counts.get(u.id, (None, None))[1],
            )
            for u in items
        ],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.patch("/{user_id}")
def patch_user(
    request: Request, user_id: uuid.UUID, body: UserActivate, actor: Admin, db: DB
) -> UserOut:
    user = users_service.set_active(db, actor, user_id, body.is_active, ip=get_client_ip(request))
    return UserOut.from_user(user)
