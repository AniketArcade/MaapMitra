from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DB, require_cron_secret
from app.schemas.jobs import ExpiryCheckSummary
from app.services import certificates as certificates_service

router = APIRouter(prefix="/jobs", tags=["jobs"])

CronAuth = Annotated[None, Depends(require_cron_secret)]


@router.post("/expiry-check")
def expiry_check(_: CronAuth, db: DB) -> ExpiryCheckSummary:
    return ExpiryCheckSummary(**certificates_service.expiry_check(db))
