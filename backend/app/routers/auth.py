from fastapi import APIRouter, Request, Response, status

from app.core.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.core.deps import DB, CurrentUser, get_client_ip
from app.core.rate_limit import limiter
from app.core.security import access_ttl
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services.auth import AuthResult

router = APIRouter(prefix="/auth", tags=["auth"])


def _respond(response: Response, result: AuthResult) -> AuthResponse:
    set_auth_cookies(response, result.refresh_token)
    return AuthResponse(
        access_token=result.access_token,
        expires_in=int(access_ttl().total_seconds()),
        user=UserOut.from_user(result.user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
def register(request: Request, response: Response, body: RegisterRequest, db: DB) -> AuthResponse:
    return _respond(response, auth_service.register(db, body, ip=get_client_ip(request)))


@router.post("/login")
@limiter.limit("20/minute")
def login(request: Request, response: Response, body: LoginRequest, db: DB) -> AuthResponse:
    return _respond(response, auth_service.login(db, body, ip=get_client_ip(request)))


@router.post("/refresh")
def refresh(request: Request, response: Response, db: DB) -> AuthResponse:
    raw = request.cookies.get(REFRESH_COOKIE)
    return _respond(response, auth_service.refresh(db, raw, ip=get_client_ip(request)))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DB) -> None:
    auth_service.logout(db, request.cookies.get(REFRESH_COOKIE), ip=get_client_ip(request))
    clear_auth_cookies(response)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)
