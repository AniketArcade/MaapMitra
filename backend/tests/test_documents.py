import hashlib
import threading
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.rate_limit import upload_window
from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Document
from app.services import documents as documents_service
from app.services.documents import sanitize_filename, sniff
from tests.conftest import BASE_URL, JPEG_BYTES, PDF_BYTES, PNG_BYTES, auth_header, upload
from tests.helpers import audit_rows

MiB = 1024 * 1024


def _count(application_id) -> int:  # noqa: ANN001
    with SessionLocal() as s:
        return s.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.application_id == application_id)
        )


@pytest.fixture
def draft(make_user, make_application):  # noqa: ANN001, ANN201
    owner = make_user(Role.BUSINESS)
    return owner, make_application(owner)


@pytest.mark.parametrize(
    ("data", "filename", "claimed", "detected", "ext"),
    [
        (PDF_BYTES, "invoice.pdf", "application/pdf", "application/pdf", "pdf"),
        (PNG_BYTES, "photo.png", "image/png", "image/png", "png"),
        (JPEG_BYTES, "photo.jpeg", "image/jpeg", "image/jpeg", "jpg"),
        (PNG_BYTES, "sneaky.pdf", "application/pdf", "image/png", "png"),  # content wins
        (PDF_BYTES, "doc.txt", "text/plain", "application/pdf", "pdf"),
    ],
)
def test_detected_type_wins(
    client: TestClient, draft, storage, data, filename, claimed, detected, ext
) -> None:  # noqa: ANN001
    owner, app = draft
    res = upload(client, owner, app.id, data=data, filename=filename, content_type=claimed)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["content_type"] == detected
    assert body["original_filename"].endswith(f".{ext}") or body["original_filename"].endswith(
        ".jpeg"
    )
    assert "storage_path" not in body and "url" not in body
    ((path, (stored, ctype)),) = storage.objects.items()
    assert path == f"applications/{app.id}/{body['id']}.{ext}"
    assert stored == data and ctype == detected
    with SessionLocal() as s:
        assert s.get(Document, body["id"]).sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "data",
    [b"MZ\x90\x00 fake exe", b"<html><script>alert(1)</script></html>", b"GIF89a....", b"%PD"],
)
def test_disallowed_types(client: TestClient, draft, storage, data: bytes) -> None:  # noqa: ANN001
    owner, app = draft
    res = upload(client, owner, app.id, data=data, filename="evil.pdf")
    assert res.status_code == 422
    assert res.json()["detail"][0]["msg"] == "Only PDF, JPG and PNG files are allowed"
    assert storage.objects == {} and _count(app.id) == 0


def test_size_limits(client: TestClient, draft, storage) -> None:  # noqa: ANN001
    owner, app = draft
    exact = b"%PDF-" + b"0" * (10 * MiB - 5)
    assert upload(client, owner, app.id, data=exact).status_code == 201
    too_big = b"%PDF-" + b"0" * (10 * MiB - 4)
    res = upload(client, owner, app.id, data=too_big)
    assert res.status_code == 413
    assert upload(client, owner, app.id, data=b"").status_code == 422
    assert _count(app.id) == 1 and len(storage.objects) == 1


def test_bad_form_fields(client: TestClient, draft) -> None:  # noqa: ANN001
    owner, app = draft
    assert upload(client, owner, app.id, document_type="PASSPORT").status_code == 422
    assert upload(client, owner, "not-a-uuid").status_code == 422
    res = client.post(
        "/api/documents",
        data={"application_id": str(app.id), "document_type": "OTHER"},
        headers=auth_header(owner),
    )
    assert res.status_code == 422  # no file


def test_document_limit(client: TestClient, draft) -> None:  # noqa: ANN001
    owner, app = draft
    for _ in range(10):
        assert upload(client, owner, app.id, "OTHER").status_code == 201
    res = upload(client, owner, app.id, "OTHER")
    assert res.status_code == 409 and "at most 10" in res.json()["detail"]


def test_concurrent_uploads_never_exceed_limit(app, draft) -> None:  # noqa: ANN001
    owner, application = draft
    statuses: list[int] = []
    barrier = threading.Barrier(11)

    def go() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        statuses.append(upload(c, owner, application.id, "OTHER").status_code)

    threads = [threading.Thread(target=go) for _ in range(11)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _count(application.id) == 10
    assert sorted(statuses) == [201] * 10 + [409]


def test_upload_racing_submit(app, client: TestClient, draft, storage) -> None:  # noqa: ANN001
    owner, application = draft
    upload(client, owner, application.id, "PROOF_OF_OWNERSHIP")
    upload(client, owner, application.id, "INSTRUMENT_PHOTO")
    in_put, release = threading.Event(), threading.Event()

    def block(_path: str) -> None:
        in_put.set()
        release.wait(5)

    storage.before_put = block
    result: dict[str, int] = {}

    def slow_upload() -> None:
        c = TestClient(app, base_url=BASE_URL)
        result["status"] = upload(c, owner, application.id, "OTHER").status_code

    t = threading.Thread(target=slow_upload)
    t.start()
    assert in_put.wait(5)
    storage.before_put = None
    res = client.patch(
        f"/api/applications/{application.id}/status",
        json={"status": "SUBMITTED"},
        headers=auth_header(owner),
    )
    assert res.status_code == 200
    release.set()
    t.join()
    assert result["status"] == 409
    assert _count(application.id) == 2
    assert len(storage.objects) == 2  # the late object was deleted again


def test_no_upload_or_delete_after_submit(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    submitted = make_application(owner, status="SUBMITTED")
    assert upload(client, owner, submitted.id, "OTHER").status_code == 409
    doc_id = client.get(f"/api/applications/{submitted.id}", headers=auth_header(owner)).json()[
        "documents"
    ][0]["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=auth_header(owner)).status_code == 409


def test_storage_failure_is_502_without_row(client: TestClient, draft, storage) -> None:  # noqa: ANN001
    owner, app = draft
    storage.fail_next_put = True
    res = upload(client, owner, app.id)
    assert (res.status_code, res.json()["detail"]) == (502, "Upload failed, please retry")
    assert _count(app.id) == 0 and storage.objects == {}


def test_commit_failure_after_put_deletes_object(
    app,
    draft,
    storage,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
) -> None:
    owner, application = draft

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(documents_service.audit, "log", boom)
    c = TestClient(app, base_url=BASE_URL, raise_server_exceptions=False)
    assert upload(c, owner, application.id).status_code == 500
    assert storage.objects == {} and _count(application.id) == 0


def test_delete_document(client: TestClient, draft, storage) -> None:  # noqa: ANN001
    owner, app = draft
    doc_id = upload(client, owner, app.id).json()["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=auth_header(owner)).status_code == 204
    assert storage.objects == {} and _count(app.id) == 0
    assert client.delete(f"/api/documents/{doc_id}", headers=auth_header(owner)).status_code == 404
    rows = audit_rows("DOCUMENT_DELETED")
    assert len(rows) == 1 and rows[0].organization_id == owner.organization_id


def test_upload_rate_limit(client: TestClient, draft) -> None:  # noqa: ANN001
    owner, app = draft
    for _ in range(60):
        upload_window.hit(str(owner.id))
    res = upload(client, owner, app.id)
    assert res.status_code == 429


def test_signed_url(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner, officer = make_user(Role.BUSINESS), make_user(Role.LM_OFFICER)
    app = make_application(owner)
    # Quote stripping is covered by test_sanitize_filename; multipart clients percent-encode quotes.
    doc_id = upload(client, owner, app.id, filename="../../my  invoice;.pdf").json()["id"]
    res = client.get(f"/api/documents/{doc_id}/url", headers=auth_header(owner))
    assert res.status_code == 200
    body = res.json()
    assert body["expires_in"] <= 300
    assert body["url"].startswith("https://")
    assert "download=" not in body["url"]  # View: served inline
    attachment = client.get(
        f"/api/documents/{doc_id}/url?disposition=attachment", headers=auth_header(owner)
    ).json()["url"]
    assert unquote(attachment).endswith("download=my invoice.pdf")
    assert (
        client.get(
            f"/api/documents/{doc_id}/url?disposition=evil", headers=auth_header(owner)
        ).status_code
        == 422
    )
    rows = audit_rows("DOCUMENT_URL_ISSUED")  # committed: visible from a fresh session
    assert len(rows) == 2 and all(r.actor_user_id == owner.id for r in rows)
    assert {r.details["disposition"] for r in rows} == {"inline", "attachment"}
    assert rows[0].organization_id == owner.organization_id
    # Officials can't reach it while the application is a draft
    assert (
        client.get(f"/api/documents/{doc_id}/url", headers=auth_header(officer)).status_code == 404
    )


def test_upload_audit(client: TestClient, draft) -> None:  # noqa: ANN001
    owner, app = draft
    body = upload(client, owner, app.id, data=PNG_BYTES, filename="p.png").json()
    rows = audit_rows("DOCUMENT_UPLOADED")
    assert len(rows) == 1
    assert rows[0].details == {
        "application_id": str(app.id),
        "document_type": "PROOF_OF_OWNERSHIP",
        "size_bytes": len(PNG_BYTES),
        "sha256": hashlib.sha256(PNG_BYTES).hexdigest(),
    }
    assert rows[0].entity_id is not None and str(rows[0].entity_id) == body["id"]


@pytest.mark.parametrize(
    ("name", "ext", "expected"),
    [
        ("invoice.pdf", "pdf", "invoice.pdf"),
        ("../../etc/passwd.pdf", "pdf", "passwd.pdf"),
        ("C:\\Users\\x\\scan.PDF", "pdf", "scan.PDF"),
        ('a";b.pdf', "pdf", "ab.pdf"),
        ("bad\x00\x1fname.png", "png", "badname.png"),
        ("  lots   of   space .jpg ", "jpg", "lots of space .jpg"),
        ("photo.jpeg", "jpg", "photo.jpeg"),
        ("", "pdf", "document.pdf"),
        (None, "png", "document.png"),
        ("...", "pdf", "document.pdf"),
        ("report", "pdf", "report.pdf"),
        ("scan.pdf", "png", "scan.pdf.png"),
    ],
)
def test_sanitize_filename(name, ext: str, expected: str) -> None:  # noqa: ANN001
    assert sanitize_filename(name, ext) == expected


def test_sanitize_long_names() -> None:
    assert len(sanitize_filename("x" * 300 + ".pdf", "pdf")) == 200
    assert sanitize_filename("x" * 300 + ".pdf", "pdf").endswith(".pdf")
    assert len(sanitize_filename("y" * 300, "png")) == 200


def test_sniff() -> None:
    assert sniff(PDF_BYTES) == ("application/pdf", "pdf")
    assert sniff(JPEG_BYTES) == ("image/jpeg", "jpg")
    assert sniff(b"") is None
