from typing import Protocol


class EmailError(Exception):
    """An email backend call failed. Messages never include credentials or the email body."""


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...
