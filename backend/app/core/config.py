from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    # Optional until storage / email features land.
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_BUCKET: str = "documents"
    RESEND_API_KEY: str | None = None

    PUBLIC_BASE_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000"
    CRON_SECRET: str

    # Number of trusted proxies in front of the app that append to X-Forwarded-For.
    # 0 = use the socket peer address. Measure on deploy (Vercel rewrite -> Render).
    TRUSTED_PROXY_HOPS: int = Field(default=0, ge=0)

    @property
    def cookie_secure(self) -> bool:
        return self.ENV != "development"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
