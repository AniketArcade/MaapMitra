from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.deps import DB, get_client_ip, require_roles
from app.core.roles import Role
from app.models.user import User
from app.schemas.user import UserCreate, UserOut
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

SuperAdmin = Annotated[User, Depends(require_roles(Role.SUPER_ADMIN))]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(request: Request, body: UserCreate, actor: SuperAdmin, db: DB) -> UserOut:
    user = users_service.create_user(db, actor, body, ip=get_client_ip(request))
    return UserOut.from_user(user)
