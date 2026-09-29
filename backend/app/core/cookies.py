from starlette.responses import Response

from app.core.config import get_settings
from app.core.security import refresh_ttl

REFRESH_COOKIE = "lm_refresh"
SESSION_COOKIE = "lm_session"  # presence flag for the frontend proxy.ts; carries no secret
REFRESH_PATH = "/api/auth"


def set_auth_cookies(response: Response, raw_refresh: str) -> None:
    secure = get_settings().cookie_secure
    max_age = int(refresh_ttl().total_seconds())
    response.set_cookie(
        REFRESH_COOKIE,
        raw_refresh,
        max_age=max_age,
        path=REFRESH_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        SESSION_COOKIE,
        "1",
        max_age=max_age,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    secure = get_settings().cookie_secure
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_PATH, httponly=True, secure=secure, samesite="lax"
    )
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="lax")
