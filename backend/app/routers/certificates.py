import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from app.core.deps import DB, get_client_ip, require_roles
from app.core.roles import Role
from app.models.user import User
from app.schemas.certificate import CertificateOut, CertificateUrl
from app.services import certificates as service
from app.services.certificates import SIGNED_URL_SECONDS

router = APIRouter(prefix="/certificates", tags=["certificates"])

Reader = Annotated[
    User,
    Depends(
        require_roles(
            Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN
        )
    ),
]


@router.get("/{certificate_id}")
def get_certificate(certificate_id: uuid.UUID, user: Reader, db: DB) -> CertificateOut:
    return CertificateOut.from_model(service.get(db, user, certificate_id))


@router.get("/{certificate_id}/pdf")
def certificate_pdf(
    request: Request,
    certificate_id: uuid.UUID,
    user: Reader,
    db: DB,
    disposition: Literal["inline", "attachment"] = "inline",
) -> CertificateUrl:
    url = service.signed_url(
        db, user, certificate_id, download=disposition == "attachment", ip=get_client_ip(request)
    )
    return CertificateUrl(url=url, expires_in=SIGNED_URL_SECONDS)
