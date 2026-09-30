import hashlib
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.application_types import (
    MAX_DOCUMENTS,
    MAX_EVIDENCE_PHOTOS,
    MAX_FILE_BYTES,
    ApplicationStatus,
    DocumentType,
)
from app.core.errors import (
    BadGateway,
    Conflict,
    Forbidden,
    NotFound,
    PayloadTooLarge,
    RateLimited,
    Unprocessable,
)
from app.core.rate_limit import upload_window
from app.core.roles import Role
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


def _count(db: Session, application_id: uuid.UUID, *, evidence: bool) -> int:
    """Business documents and inspection-evidence photos are capped independently (spec 06 A2)."""
    type_filter = (
        Document.document_type == DocumentType.INSPECTION_EVIDENCE
        if evidence
        else Document.document_type != DocumentType.INSPECTION_EVIDENCE
    )
    return (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.application_id == application_id, type_filter)
        )
        or 0
    )


def _check_upload_allowed(
    application: Application, user: User, document_type: DocumentType
) -> None:
    """DRAFT/BUSINESS for every ordinary document type (unchanged, spec 03); INSPECTION/assigned
    officer, not-yet-submitted for INSPECTION_EVIDENCE (spec 06 A1). The router now admits both
    BUSINESS and LM_OFFICER (so evidence uploads can reach this service), so each branch must
    check the actor's role explicitly — scope/status alone no longer implies it, the way a
    DRAFT-only check alone used to when only BUSINESS could reach this function at all."""
    if document_type == DocumentType.INSPECTION_EVIDENCE:
        if application.status != ApplicationStatus.INSPECTION:
            raise Conflict("Evidence photos can only be added during an active inspection")
        if application.inspection is None or application.inspection.assigned_officer_id != user.id:
            raise Forbidden("Only the assigned officer can do this")
        if application.inspection.submitted_at is not None:
            raise Conflict("This inspection has already been submitted")
    else:
        if user.role != Role.BUSINESS:
            raise Forbidden("Insufficient permissions")
        if application.status != ApplicationStatus.DRAFT:
            raise Conflict("Documents can only be added to a draft application")


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
    document_type = DocumentType(document_type)  # accept the enum or its string value
    if not upload_window.hit(str(user.id)):
        raise RateLimited("Too many uploads. Try again later.")

    # Pre-checks without a lock (spec 03 §7 step 2).
    application = applications_service.load(db, user, application_id)
    _check_upload_allowed(application, user, document_type)
    is_evidence = document_type == DocumentType.INSPECTION_EVIDENCE
    cap = MAX_EVIDENCE_PHOTOS if is_evidence else MAX_DOCUMENTS
    if _count(db, application.id, evidence=is_evidence) >= cap:
        noun = "evidence photos" if is_evidence else "documents"
        raise Conflict(f"An application can have at most {cap} {noun}")

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
        # populate_existing: the session still caches the pre-upload copy of this row.
        locked = db.scalar(
            select(Application)
            .where(Application.id == application.id)
            .options(joinedload(Application.inspection))
            # populate_existing refreshes column state from this query but does not include
            # Application.inspection (lazy="raise"): without the joinedload above, accessing it
            # would raise, even though the pre-lock `application` object already had it loaded.
            # of=Application: Postgres refuses FOR UPDATE across the nullable side of an outer
            # join (LEFT JOIN inspections), and there is no write to that side here anyway.
            .with_for_update(of=Application)
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise Conflict("Documents can only be added to a draft application")
        _check_upload_allowed(locked, user, document_type)
        if _count(db, locked.id, evidence=is_evidence) >= cap:
            noun = "evidence photos" if is_evidence else "documents"
            raise Conflict(f"An application can have at most {cap} {noun}")
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


def signed_url(
    db: Session, user: User, document_id: uuid.UUID, *, download: bool = False, ip: str
) -> str:
    """download=False: the link displays the file inline (View). True: it saves the file
    under its sanitized original name (Download)."""
    document = _load(db, user, document_id)
    try:
        url = get_storage().signed_url(
            document.storage_path,
            SIGNED_URL_SECONDS,
            document.original_filename if download else None,
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
            "disposition": "attachment" if download else "inline",
        },
        ip=ip,
    )
    db.commit()  # audit-writing GET: the service commits (spec 03 §2.4)
    return url


def delete(db: Session, user: User, document_id: uuid.UUID, *, ip: str) -> None:
    document = _load(db, user, document_id)
    application = db.scalar(
        select(Application)
        .where(Application.id == document.application_id)
        .options(joinedload(Application.inspection))
        # of=Application: Postgres refuses FOR UPDATE across the nullable side of an outer join
        # (LEFT JOIN inspections), and there is no write to that side here anyway.
        .with_for_update(of=Application)
        .execution_options(populate_existing=True)
    )
    if application is None:
        raise Conflict("Documents can only be removed from a draft application")
    if document.document_type == DocumentType.INSPECTION_EVIDENCE:
        # Symmetric with the upload rule (spec 06 A1): the assigned officer, not yet submitted.
        if application.inspection is None or application.inspection.assigned_officer_id != user.id:
            raise Forbidden("Only the assigned officer can do this")
        if application.inspection.submitted_at is not None:
            raise Conflict("This inspection has already been submitted")
    else:
        if user.role != Role.BUSINESS:
            raise Forbidden("Insufficient permissions")
        if application.status != ApplicationStatus.DRAFT:
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
