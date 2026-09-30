from app.email.base import EmailError


class MemoryEmail:
    """In-process email for tests/local dev. Not for production."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail_next_send = False

    def send(self, *, to: str, subject: str, body: str) -> None:
        if self.fail_next_send:
            self.fail_next_send = False
            raise EmailError("simulated send failure")
        self.sent.append({"to": to, "subject": subject, "body": body})

    def clear(self) -> None:
        self.sent.clear()
        self.fail_next_send = False
