import json
import logging

import httpx2
import pytest

from app.storage import StorageError, SupabaseStorage

KEY = "sb_secret_test_key_1234567890abcdefghij"


def _storage(handler) -> SupabaseStorage:  # noqa: ANN001
    return SupabaseStorage(
        "https://proj.supabase.co/", KEY, "documents", transport=httpx2.MockTransport(handler)
    )


def test_put_request() -> None:
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(
            method=request.method,
            url=str(request.url),
            auth=request.headers["authorization"],
            apikey=request.headers["apikey"],
            ctype=request.headers["content-type"],
            upsert=request.headers["x-upsert"],
            body=request.content,
        )
        return httpx2.Response(200, json={"Key": "documents/x"})

    _storage(handler).put("applications/a/b.pdf", b"%PDF-1", "application/pdf")
    assert seen["method"] == "POST"
    assert (
        seen["url"] == "https://proj.supabase.co/storage/v1/object/documents/applications/a/b.pdf"
    )
    assert seen["auth"] == f"Bearer {KEY}" and seen["apikey"] == KEY
    assert (seen["ctype"], seen["upsert"], seen["body"]) == ("application/pdf", "false", b"%PDF-1")


def test_signed_url_is_absolute_with_download_name() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/storage/v1/object/sign/documents/applications/a/b.pdf"
        assert json.loads(request.content) == {"expiresIn": 300}
        return httpx2.Response(
            200, json={"signedURL": "/object/sign/documents/applications/a/b.pdf?token=abc"}
        )

    url = _storage(handler).signed_url("applications/a/b.pdf", 300, "my invoice.pdf")
    assert url == (
        "https://proj.supabase.co/storage/v1/object/sign/documents/applications/a/b.pdf"
        "?token=abc&download=my%20invoice.pdf"
    )


def test_delete_request() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert (request.method, request.url.path) == ("DELETE", "/storage/v1/object/documents")
        assert json.loads(request.content) == {"prefixes": ["a.pdf", "b.png"]}
        return httpx2.Response(200, json=[])

    _storage(handler).delete(["a.pdf", "b.png"])


def test_errors_never_leak_the_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def denied(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json={"message": "invalid key"})

    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("boom", request=request)

    for handler in (denied, down):
        with pytest.raises(StorageError) as exc_info:
            _storage(handler).put("x.pdf", b"%PDF-", "application/pdf")
        assert KEY not in str(exc_info.value)
    assert KEY not in caplog.text


def test_ensure_bucket_creates_private_bucket() -> None:
    created = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            return httpx2.Response(404, json={"error": "not found"})
        created.update(json.loads(request.content))
        return httpx2.Response(200, json={"name": "documents"})

    assert _storage(handler).ensure_bucket(
        file_size_limit=10, allowed_mime_types=["application/pdf"]
    )
    assert created == {
        "id": "documents",
        "name": "documents",
        "public": False,
        "file_size_limit": 10,
        "allowed_mime_types": ["application/pdf"],
    }


def test_ensure_bucket_is_idempotent() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        return httpx2.Response(200, json={"id": "documents", "public": False})

    assert _storage(handler).ensure_bucket(file_size_limit=10, allowed_mime_types=[]) is False
