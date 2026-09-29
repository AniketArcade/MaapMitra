import os

# Force test settings before any app import. Env vars take precedence over backend/.env.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://localhost/lm_test")
if "supabase" in TEST_DATABASE_URL:
    raise RuntimeError("Refusing to run tests against Supabase. Use a local test database.")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-00"
os.environ["CRON_SECRET"] = "test-cron-secret"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["TRUSTED_PROXY_HOPS"] = "0"

import uuid  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.rate_limit import reset_rate_limits  # noqa: E402
from app.core.roles import OrgType, Role  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Instrument, Organization, User  # noqa: E402
from app.schemas.instrument import InstrumentCreate  # noqa: E402
from app.services import instruments as instruments_service  # noqa: E402

PASSWORD = "Password123!"
BASE_URL = "https://testserver"  # cookies are Secure outside ENV=development
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> Iterator[None]:
    cfg = Config(str(ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    reset_rate_limits()
    yield
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE audit_logs, instruments, refresh_tokens, users, organizations CASCADE")
        )


@pytest.fixture
def app():  # noqa: ANN201
    return create_app()


@pytest.fixture
def client(app) -> TestClient:  # noqa: ANN001
    return TestClient(app, base_url=BASE_URL)


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def _make(
        role: Role = Role.BUSINESS,
        email: str | None = None,
        *,
        org_state: str = "JH",
        org_district: str = "DHN",
        **kw: object,
    ) -> User:
        org = None
        if role in (Role.BUSINESS, Role.GATC):
            org = Organization(
                type=OrgType.GATC if role == Role.GATC else OrgType.BUSINESS,
                name=f"Org {uuid.uuid4().hex[:6]}",
                state_code=org_state,
                district_code=org_district,
            )
        scope: dict[str, object] = {}
        if role == Role.STATE_ADMIN:
            scope = {"state_code": "JH"}
        elif role in (Role.DISTRICT_ADMIN, Role.LM_OFFICER):
            scope = {"state_code": "JH", "district_code": "DHN"}
        user = User(
            email=email or f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@test.demo",
            password_hash=hash_password(kw.pop("password", PASSWORD)),  # type: ignore[arg-type]
            full_name=f"Test {role.value}",
            role=role,
            organization=org,
            **{**scope, **kw},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def register_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "organization_name": "ABC Traders",
        "state_code": "JH",
        "district_code": "DHN",
        "full_name": "Owner",
        "email": "owner@abc.demo",
        "password": PASSWORD,
    }
    body.update(overrides)
    return body


def instrument_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "instrument_type": "WEIGHING_SCALE",
        "manufacturer": "Essae Teraoka",
        "model": "DS-252",
        "serial_number": f"SN-{uuid.uuid4().hex[:8].upper()}",
        "capacity": 500,
        "capacity_unit": "kg",
        "address": "Bank More, Dhanbad",
    }
    body.update(overrides)
    return body


@pytest.fixture
def make_instrument(db: Session) -> Callable[..., Instrument]:
    """Creates through the service, so UIDs and defaults are real."""

    def _make(owner: User, **overrides: object) -> Instrument:
        with SessionLocal() as s:
            user = s.get(User, owner.id)
            assert user is not None
            body = InstrumentCreate.model_validate(instrument_body(**overrides))
            instrument = instruments_service.create(s, user, body, ip="test")
            return instrument

    return _make
