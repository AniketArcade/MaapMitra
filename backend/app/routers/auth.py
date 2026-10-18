from fastapi import APIRouter, Request, Response, status

from app.core.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.core.deps import DB, CurrentUser, get_client_ip
from app.core.rate_limit import limiter
from app.core.security import access_ttl
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, RegisterRequest
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services.auth import AuthResult

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_mobile(request: Request) -> bool:
    """Native apps have no cookie jar: they send `X-Client: mobile` and store the token."""
    return request.headers.get("x-client", "").strip().lower() == "mobile"


def _respond(request: Request, response: Response, result: AuthResult) -> AuthResponse:
    mobile = _is_mobile(request)
    if not mobile:
        set_auth_cookies(response, result.refresh_token)
    return AuthResponse(
        access_token=result.access_token,
        expires_in=int(access_ttl().total_seconds()),
        user=UserOut.from_user(result.user),
        refresh_token=result.refresh_token if mobile else None,
    )


def _refresh_token(request: Request, body: RefreshRequest | None) -> str | None:
    # Mobile ignores cookies entirely; web ignores the body.
    if _is_mobile(request):
        return body.refresh_token if body else None
    return request.cookies.get(REFRESH_COOKIE)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
def register(request: Request, response: Response, body: RegisterRequest, db: DB) -> AuthResponse:
    result = auth_service.register(db, body, ip=get_client_ip(request))
    return _respond(request, response, result)


@router.post("/login")
@limiter.limit("20/minute")
def login(request: Request, response: Response, body: LoginRequest, db: DB) -> AuthResponse:
    result = auth_service.login(db, body, ip=get_client_ip(request))
    return _respond(request, response, result)


@router.post("/refresh")
def refresh(
    request: Request, response: Response, db: DB, body: RefreshRequest | None = None
) -> AuthResponse:
    raw = _refresh_token(request, body)
    return _respond(request, response, auth_service.refresh(db, raw, ip=get_client_ip(request)))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, response: Response, db: DB, body: RefreshRequest | None = None
) -> None:
    auth_service.logout(db, _refresh_token(request, body), ip=get_client_ip(request))
    if not _is_mobile(request):
        clear_auth_cookies(response)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)
