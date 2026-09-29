import hashlib
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.application_types import (
    MAX_DOCUMENTS,
    MAX_FILE_BYTES,
    ApplicationStatus,
    DocumentType,
)
from app.core.errors import (
    BadGateway,
    Conflict,
    NotFound,
    PayloadTooLarge,
    RateLimited,
    Unprocessable,
)
from app.core.rate_limit import upload_window
from app.models.application import Application
from app.models.document import Document
from app.models.user import User
from app.services import applications as applications_service
from app.services import audit
from app.services.scoping import scope_documents
from app.storage import StorageError, get_storage

SIGNED_URL_SECONDS = 300  # never more than 5 minutes
FILENAME_MAX = 200

# Magic bytes -> (detected content type, extension). The client's claim is never trusted.
_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)
_EXTENSION_ALIASES = {"jpg": (".jpg", ".jpeg"), "pdf": (".pdf",), "png": (".png",)}
_UNSAFE = re.compile(r"[\x00-\x1f\x7f\"'\\;]")


def sniff(data: bytes) -> tuple[str, str] | None:
    for magic, content_type, ext in _SIGNATURES:
        if data.startswith(magic):
            return content_type, ext
    return None


def sanitize_filename(name: str | None, ext: str) -> str:
    """The only filename ever shown in the UI or placed in download=. Never used in paths."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = " ".join(_UNSAFE.sub("", base).split()).strip(" .")
    if not base:
        base = "document"
    if not base.lower().endswith(_EXTENSION_ALIASES[ext]):
        base = f"{base[: FILENAME_MAX - len(ext) - 1]}.{ext}"
    elif len(base) > FILENAME_MAX:
        stem, dot, suffix = base.rpartition(".")
        base = f"{stem[: FILENAME_MAX - len(suffix) - 1]}{dot}{suffix}"
    return base


def _count(db: Session, application_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.application_id == application_id)
        )
        or 0
    )


def upload(
    db: Session,
    user: User,
    *,
    application_id: uuid.UUID,
    document_type: DocumentType,
    filename: str | None,
    data: bytes,
    ip: str,
) -> Document:
    if not upload_window.hit(str(user.id)):
        raise RateLimited("Too many uploads. Try again later.")

    # Pre-checks without a lock (spec 03 §7 step 2).
    application = applications_service.load(db, user, application_id)
    if application.status != ApplicationStatus.DRAFT:
        raise Conflict("Documents can only be added to a draft application")
    if _count(db, application.id) >= MAX_DOCUMENTS:
        raise Conflict(f"An application can have at most {MAX_DOCUMENTS} documents")

    if len(data) > MAX_FILE_BYTES:
        raise PayloadTooLarge("File is too large (maximum 10 MB)")
    if not data:
        raise Unprocessable("The file is empty", field="file")
    detected = sniff(data)
    if detected is None:
        raise Unprocessable("Only PDF, JPG and PNG files are allowed", field="file")
    content_type, ext = detected

    document_id = uuid.uuid4()
    path = f"applications/{application.id}/{document_id}.{ext}"
    organization_id = application.organization_id
    db.commit()  # end the read transaction; nothing is held while the object uploads

    storage = get_storage()
    try:
        storage.put(path, data, content_type)
    except StorageError:
        raise BadGateway("Upload failed, please retry") from None

    try:
        # Re-check under the application row lock: serialises with submit, delete and
        # concurrent uploads, so no document can appear after submit or exceed the limit.
        locked = db.scalar(
            select(Application).where(Application.id == application.id).with_for_update()
        )
        if locked is None or locked.status != ApplicationStatus.DRAFT:
            raise Conflict("Documents can only be added to a draft application")
        if _count(db, locked.id) >= MAX_DOCUMENTS:
            raise Conflict(f"An application can have at most {MAX_DOCUMENTS} documents")
        sha256 = hashlib.sha256(data).hexdigest()
        document = Document(
            id=document_id,
            application_id=locked.id,
            organization_id=organization_id,
            document_type=document_type,
            original_filename=sanitize_filename(filename, ext),
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha256,
            storage_path=path,
            uploaded_by=user.id,
        )
        db.add(document)
        audit.log(
            db,
            actor=user,
            action="DOCUMENT_UPLOADED",
            entity_type="document",
            entity_id=document_id,
            organization_id=organization_id,
            details={
                "application_id": str(locked.id),
                "document_type": document_type.value,
                "size_bytes": len(data),
                "sha256": sha256,
            },
            ip=ip,
        )
        db.commit()
    except BaseException:
        db.rollback()
        applications_service.delete_objects_best_effort([path])  # accepted: rare orphans
        raise
    return document


def _load(db: Session, user: User, document_id: uuid.UUID) -> Document:
    document = db.scalar(scope_documents(select(Document), user).where(Document.id == document_id))
    if document is None:
        raise NotFound("Document not found")
    return document


def signed_url(db: Session, user: User, document_id: uuid.UUID, *, ip: str) -> str:
    document = _load(db, user, document_id)
    try:
        url = get_storage().signed_url(
            document.storage_path, SIGNED_URL_SECONDS, document.original_filename
        )
    except StorageError:
        raise BadGateway("Could not create a download link, please retry") from None
    audit.log(
        db,
        actor=user,
        action="DOCUMENT_URL_ISSUED",
        entity_type="document",
        entity_id=document.id,
        organization_id=document.organization_id,
        details={
            "application_id": str(document.application_id),
            "document_type": document.document_type.value,
        },
        ip=ip,
    )
    db.commit()  # audit-writing GET: the service commits (spec 03 §2.4)
    return url


def delete(db: Session, user: User, document_id: uuid.UUID, *, ip: str) -> None:
    document = _load(db, user, document_id)
    application = db.scalar(
        select(Application).where(Application.id == document.application_id).with_for_update()
    )
    if application is None or application.status != ApplicationStatus.DRAFT:
        raise Conflict("Documents can only be removed from a draft application")
    path = document.storage_path
    audit.log(
        db,
        actor=user,
        action="DOCUMENT_DELETED",
        entity_type="document",
        entity_id=document.id,
        organization_id=document.organization_id,
        details={
            "application_id": str(document.application_id),
            "document_type": document.document_type.value,
        },
        ip=ip,
    )
    db.delete(document)
    db.commit()
    applications_service.delete_objects_best_effort([path])
