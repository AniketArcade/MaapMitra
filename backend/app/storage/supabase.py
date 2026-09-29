"""Supabase Storage via its REST API (no SDK). The service role key stays server-side."""

import logging
from urllib.parse import quote

import httpx2

from app.storage.base import StorageError

log = logging.getLogger(__name__)


class SupabaseStorage:
    def __init__(
        self,
        url: str,
        service_key: str,
        bucket: str,
        *,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self._client = httpx2.Client(
            base_url=self.base,
            headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
            timeout=httpx2.Timeout(30.0, connect=5.0),
            transport=transport,
        )

    def _call(self, op: str, method: str, url: str, **kwargs: object) -> httpx2.Response:
        try:
            response = self._client.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx2.HTTPError as exc:
            # Log the operation and error class only: never headers (they hold the key).
            log.warning("storage %s failed: %s", op, type(exc).__name__)
            raise StorageError(f"storage {op} failed") from None
        if response.status_code >= 400:
            log.warning("storage %s failed: HTTP %s", op, response.status_code)
            raise StorageError(f"storage {op} failed (HTTP {response.status_code})")
        return response

    def _object(self, path: str) -> str:
        return f"{quote(self.bucket)}/{quote(path)}"

    def put(self, path: str, data: bytes, content_type: str) -> None:
        self._call(
            "put",
            "POST",
            f"/object/{self._object(path)}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "false"},
        )

    def delete(self, paths: list[str]) -> None:
        if paths:
            self._call(
                "delete", "DELETE", f"/object/{quote(self.bucket)}", json={"prefixes": paths}
            )

    def signed_url(self, path: str, expires_in: int, download_name: str) -> str:
        response = self._call(
            "sign", "POST", f"/object/sign/{self._object(path)}", json={"expiresIn": expires_in}
        )
        relative = response.json().get("signedURL") or response.json().get("signedUrl")
        if not relative:
            raise StorageError("storage sign returned no URL")
        # The API returns a path relative to /storage/v1 (e.g. "/object/sign/...?token=...").
        separator = "&" if "?" in relative else "?"
        return f"{self.base}{relative}{separator}download={quote(download_name)}"

    def ensure_bucket(self, *, file_size_limit: int, allowed_mime_types: list[str]) -> bool:
        """Create the private bucket if missing. Returns True if it was created."""
        try:
            response = self._client.get(f"/bucket/{quote(self.bucket)}")
        except httpx2.HTTPError:
            raise StorageError("storage bucket lookup failed") from None
        if response.status_code == 200:
            return False
        self._call(
            "create-bucket",
            "POST",
            "/bucket",
            json={
                "id": self.bucket,
                "name": self.bucket,
                "public": False,
                "file_size_limit": file_size_limit,
                "allowed_mime_types": allowed_mime_types,
            },
        )
        return True
