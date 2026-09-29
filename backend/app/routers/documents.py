import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.core.application_types import MAX_FILE_BYTES, DocumentType
from app.core.deps import DB, get_client_ip, require_roles
from app.core.roles import Role
from app.models.user import User
from app.schemas.document import DocumentOut, DocumentUrl
from app.services import documents as service
from app.services.documents import SIGNED_URL_SECONDS

router = APIRouter(prefix="/documents", tags=["documents"])

Reader = Annotated[
    User,
    Depends(
        require_roles(
            Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN
        )
    ),
]
Owner = Annotated[User, Depends(require_roles(Role.BUSINESS))]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    user: Owner,
    db: DB,
    application_id: Annotated[uuid.UUID, Form()],
    document_type: Annotated[DocumentType, Form()],
    file: UploadFile,
) -> DocumentOut:
    # The body-size middleware already capped the request; read one extra byte to detect > 10 MiB.
    data = await file.read(MAX_FILE_BYTES + 1)
    document = await run_in_threadpool(
        service.upload,
        db,
        user,
        application_id=application_id,
        document_type=document_type,
        filename=file.filename,
        data=data,
        ip=get_client_ip(request),
    )
    return DocumentOut.from_model(document)


@router.get("/{document_id}/url")
def document_url(request: Request, document_id: uuid.UUID, user: Reader, db: DB) -> DocumentUrl:
    url = service.signed_url(db, user, document_id, ip=get_client_ip(request))
    return DocumentUrl(url=url, expires_in=SIGNED_URL_SECONDS)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(request: Request, document_id: uuid.UUID, user: Owner, db: DB) -> None:
    service.delete(db, user, document_id, ip=get_client_ip(request))
