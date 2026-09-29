from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.db.session import ping_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(response: Response, db: bool = False) -> HealthResponse:
    """Liveness. Pass `?db=true` to also check database connectivity."""
    version = get_settings().APP_VERSION
    if not db:
        return HealthResponse(status="ok", version=version)
    if ping_db():
        return HealthResponse(status="ok", version=version, db="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", version=version, db="unreachable")
