from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
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

    RESEND_API_KEY: str | None = None  # optional until email lands

    PUBLIC_BASE_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000"
    CRON_SECRET: str

    # Number of trusted proxies in front of the app that append to X-Forwarded-For.
    # 0 = use the socket peer address. Measure on deploy (Vercel rewrite -> Render).
    TRUSTED_PROXY_HOPS: int = Field(default=0, ge=0)

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

    @property
    def cookie_secure(self) -> bool:
        return self.ENV != "development"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
