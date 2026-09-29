import asyncio

from app.middleware.body_limit import BodySizeLimitMiddleware

LIMIT = 1000


def _run(headers: list[tuple[bytes, bytes]], chunks: list[bytes], *, path: str = "/api/documents"):  # noqa: ANN202
    received: list[int] = []
    sent: list[dict] = []
    app_called = []

    async def inner(scope, receive, send) -> None:  # noqa: ANN001
        app_called.append(True)
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive() -> dict:
        received.append(1)
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = BodySizeLimitMiddleware(
        inner, path="/api/documents", method="POST", max_bytes=LIMIT
    )
    scope = {"type": "http", "method": "POST", "path": path, "headers": headers}
    asyncio.run(middleware(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, len(received), bool(app_called)


def test_declared_length_over_limit_rejected_without_reading() -> None:
    status, reads, called = _run([(b"content-length", b"5000")], [b"x" * 5000])
    assert (status, reads, called) == (413, 0, False)


def test_missing_or_bad_length_is_411() -> None:
    assert _run([], [b"x"])[0] == 411
    assert _run([(b"content-length", b"abc")], [b"x"])[0] == 411


def test_lying_length_caught_while_streaming() -> None:
    status, _, called = _run([(b"content-length", b"10")], [b"x" * 600, b"x" * 600])
    assert status == 413 and called


def test_within_limit_passes_through() -> None:
    assert _run([(b"content-length", b"900")], [b"x" * 900])[0] == 201


def test_other_paths_untouched() -> None:
    assert _run([], [b"x" * 5000], path="/api/instruments")[0] == 201
