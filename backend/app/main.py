from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.application_types import MAX_UPLOAD_REQUEST_BYTES
from app.core.config import get_settings
from app.core.cookies import clear_auth_cookies
from app.core.errors import DomainError, Unprocessable
from app.core.rate_limit import limiter
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.routers import (
    admin,
    applications,
    audit,
    auth,
    certificates,
    documents,
    gatc,
    health,
    inspections,
    instruments,
    jobs,
    organizations,
    public,
    users,
)


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    detail: object = exc.detail
    if isinstance(exc, Unprocessable) and exc.field:
        # Same shape as FastAPI's request validation errors, so clients map it to the field.
        detail = [{"loc": ["body", exc.field], "msg": exc.detail, "type": "value_error"}]
    response = JSONResponse({"detail": detail}, status_code=exc.status_code, headers=headers)
    if exc.clear_cookies:
        clear_auth_cookies(response)
    return response


async def rate_limit_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Too many requests. Try again later."}, status_code=429)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Legal Metrology API", version=settings.APP_VERSION)

    app.state.limiter = limiter
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # Browser traffic arrives same-origin via the Next.js rewrite; CORS covers direct calls.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Outermost: rejects oversized uploads before multipart parsing starts.
    app.add_middleware(
        BodySizeLimitMiddleware,
        path="/api/documents",
        method="POST",
        max_bytes=MAX_UPLOAD_REQUEST_BYTES,
    )

    for router in (
        health.router,
        auth.router,
        users.router,
        instruments.router,
        applications.router,
        documents.router,
        inspections.router,
        certificates.router,
        public.router,
        jobs.router,
        admin.router,
        gatc.router,
        audit.router,
        organizations.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
