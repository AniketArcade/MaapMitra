"""Resend via its REST API (no SDK) — same choice app/storage/supabase.py already made for the
same reason: one fewer dependency for a single "call one REST API with a bearer key" integration."""

import logging

import httpx2

from app.email.base import EmailError

log = logging.getLogger(__name__)


class ResendEmail:
    def __init__(
        self,
        api_key: str,
        from_email: str,
        *,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self.from_email = from_email
        self._client = httpx2.Client(
            base_url="https://api.resend.com",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx2.Timeout(30.0, connect=5.0),
            transport=transport,
        )

    def send(self, *, to: str, subject: str, body: str) -> None:
        try:
            response = self._client.post(
                "/emails",
                json={"from": self.from_email, "to": [to], "subject": subject, "text": body},
            )
        except httpx2.HTTPError as exc:
            # Log the error class only: never headers (they hold the key) or the body.
            log.warning("email send failed: %s", type(exc).__name__)
            raise EmailError("email send failed") from None
        if response.status_code >= 400:
            log.warning("email send failed: HTTP %s", response.status_code)
            raise EmailError(f"email send failed (HTTP {response.status_code})")
