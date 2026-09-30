from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration. The only place that reads the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_VERSION: str = "0.1.0"
    ENV: Literal["development", "test", "production"] = "development"

    DATABASE_URL: str
    JWT_SECRET: str = Field(min_length=32)
    JWT_ACCESS_TTL_MIN: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7

    # Document storage. "memory" is for tests only.
    STORAGE_BACKEND: Literal["supabase", "memory"] = "supabase"
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None  # backend only, never logged or returned
    SUPABASE_BUCKET: str = "documents"

    # Email (step 10). "memory" is for tests/local dev.
    EMAIL_BACKEND: Literal["resend", "memory"] = "resend"
    RESEND_API_KEY: str | None = None
    RESEND_FROM_EMAIL: str | None = None

    PUBLIC_BASE_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000"
    CRON_SECRET: str

    # Number of trusted proxies in front of the app that append to X-Forwarded-For.
    # 0 = use the socket peer address. Measure on deploy (Vercel rewrite -> Render).
    TRUSTED_PROXY_HOPS: int = Field(default=0, ge=0)

    # Scheduling (step 5). ASSUMPTION: deployment serves India; change if not.
    APP_TIMEZONE: str = "Asia/Kolkata"
    SCHEDULING_MAX_DAYS_AHEAD: int = Field(default=180, ge=1)

    # Certificates (step 8). ASSUMPTION: not a real Legal Metrology validity rule.
    CERTIFICATE_VALIDITY_YEARS: int = Field(default=2, ge=1)

    # Expiry reminders (step 10). ASSUMPTION: not a real Legal Metrology rule.
    EXPIRY_REMINDER_30D_DAYS: int = Field(default=30, ge=1)
    EXPIRY_REMINDER_7D_DAYS: int = Field(default=7, ge=1)

    @field_validator("SUPABASE_URL")
    @classmethod
    def origin_only(cls, v: str | None) -> str | None:
        """Keep scheme://host only. The dashboard also shows URLs ending in /rest/v1 (Data API);
        pasting one would send every Storage call to /rest/v1/storage/v1/... and 404."""
        if not v:
            return v
        parts = urlsplit(v.strip())
        return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else v.strip()

    @model_validator(mode="after")
    def check_storage(self) -> Self:
        if self.STORAGE_BACKEND != "supabase":
            return self
        url, key = self.SUPABASE_URL or "", self.SUPABASE_SERVICE_ROLE_KEY or ""
        # Catches unset values and placeholders copied from .env.example.
        if not url.startswith("https://") or "<" in url:
            raise ValueError("SUPABASE_URL must be set to https://<project-ref>.supabase.co")
        if len(key) < 30 or key.startswith("#") or " " in key:
            raise ValueError(
                "SUPABASE_SERVICE_ROLE_KEY must be set (Supabase > Project Settings > API)"
            )
        if not self.SUPABASE_BUCKET:
            raise ValueError("SUPABASE_BUCKET must be set")
        return self

    @model_validator(mode="after")
    def check_email(self) -> Self:
        if self.EMAIL_BACKEND != "resend":
            return self
        key, sender = self.RESEND_API_KEY or "", self.RESEND_FROM_EMAIL or ""
        if len(key) < 10 or key.startswith("#"):
            raise ValueError("RESEND_API_KEY must be set (Resend > API Keys)")
        if "@" not in sender:
            raise ValueError("RESEND_FROM_EMAIL must be set to a valid sender address")
        return self

    @property
    def cookie_secure(self) -> bool:
        return self.ENV != "development"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


class ConfigError(RuntimeError):
    """Invalid configuration. The message never contains setting values (they hold secrets)."""


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        # Pydantic's own message embeds the input values; report field names and reasons only.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'settings'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"Invalid configuration: {problems}") from None
