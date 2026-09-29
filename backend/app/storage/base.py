from typing import Protocol


class StorageError(Exception):
    """A storage backend call failed. Messages never include credentials."""


class Storage(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> None: ...

    def delete(self, paths: list[str]) -> None: ...

    def signed_url(self, path: str, expires_in: int, download_name: str | None) -> str:
        """download_name=None serves inline (view); a name forces a download with that name."""
        ...
