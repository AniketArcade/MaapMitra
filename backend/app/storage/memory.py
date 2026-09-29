from collections.abc import Callable
from urllib.parse import quote

from app.storage.base import StorageError


class MemoryStorage:
    """In-process storage for tests. Not for development or production."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_next_put = False
        self.before_put: Callable[[str], None] | None = None  # test hook (e.g. to block)

    def put(self, path: str, data: bytes, content_type: str) -> None:
        if self.before_put:
            self.before_put(path)
        if self.fail_next_put:
            self.fail_next_put = False
            raise StorageError("simulated upload failure")
        if path in self.objects:
            raise StorageError("object already exists")
        self.objects[path] = (data, content_type)

    def delete(self, paths: list[str]) -> None:
        for path in paths:
            self.objects.pop(path, None)

    def signed_url(self, path: str, expires_in: int, download_name: str) -> str:
        if path not in self.objects:
            raise StorageError("object not found")
        return (
            f"https://storage.test/object/sign/{quote(path)}"
            f"?token=test&expires_in={expires_in}&download={quote(download_name)}"
        )

    def clear(self) -> None:
        self.objects.clear()
        self.fail_next_put = False
        self.before_put = None
