from fastapi import APIRouter, Request

from app.core.deps import DB
from app.core.rate_limit import limiter
from app.schemas.instrument import RegionMeta
from app.schemas.public import PublicVerifyOut
from app.services import certificates as certificates_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/verify/{certificate_number}")
@limiter.limit("30/minute")
def verify(request: Request, certificate_number: str, db: DB) -> PublicVerifyOut:
    certificate = certificates_service.public_verify(db, certificate_number)
    return PublicVerifyOut.from_model(certificate)


# No auth: the registration form (pre-account) needs the state/district list to render its
# cascading selects, the same REGIONS data GET /instruments/meta already serves to logged-in users.
@router.get("/regions")
def regions() -> list[RegionMeta]:
    return RegionMeta.build_all()
