from fastapi import APIRouter, Request

from app.core.deps import DB
from app.core.rate_limit import limiter
from app.schemas.public import PublicVerifyOut
from app.services import certificates as certificates_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/verify/{certificate_number}")
@limiter.limit("30/minute")
def verify(request: Request, certificate_number: str, db: DB) -> PublicVerifyOut:
    certificate = certificates_service.public_verify(db, certificate_number)
    return PublicVerifyOut.from_model(certificate)
