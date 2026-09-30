from functools import lru_cache

from app.core.config import get_settings
from app.email.base import EmailError, EmailSender
from app.email.memory import MemoryEmail
from app.email.resend import ResendEmail

__all__ = ["EmailError", "EmailSender", "MemoryEmail", "ResendEmail", "get_email"]


@lru_cache
def get_email() -> EmailSender:
    s = get_settings()
    if s.EMAIL_BACKEND == "memory":
        return MemoryEmail()
    assert s.RESEND_API_KEY and s.RESEND_FROM_EMAIL  # enforced by Settings
    return ResendEmail(s.RESEND_API_KEY, s.RESEND_FROM_EMAIL)
