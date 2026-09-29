from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden
from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import audit


def create_user(db: Session, actor: User, body: UserCreate, *, ip: str) -> User:
    if actor.role != Role.SUPER_ADMIN:  # defence in depth; the router also enforces this
        raise Forbidden("Insufficient permissions")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password.get_secret_value()),
        full_name=body.full_name,
        phone=body.phone,
        role=Role(body.role),
        state_code=body.state_code,
        district_code=body.district_code,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Email already registered") from exc

    audit.log(
        db,
        action="USER_CREATED",
        actor=actor.id,
        entity_type="user",
        entity_id=user.id,
        details={
            "role": user.role.value,
            "state_code": user.state_code,
            "district_code": user.district_code,
        },
        ip=ip,
    )
    db.commit()
    return user
