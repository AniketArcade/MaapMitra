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
os.environ["STORAGE_BACKEND"] = "memory"
os.environ["EMAIL_BACKEND"] = "memory"

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
from app.email import MemoryEmail, get_email  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Application, Instrument, Organization, User  # noqa: E402
from app.schemas.instrument import InstrumentCreate  # noqa: E402
from app.services import instruments as instruments_service  # noqa: E402
from app.storage import MemoryStorage, get_storage  # noqa: E402

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
    storage = get_storage()
    assert isinstance(storage, MemoryStorage)
    storage.clear()
    email = get_email()
    assert isinstance(email, MemoryEmail)
    email.clear()
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE audit_logs, documents, application_status_history, applications, "
                "instruments, refresh_tokens, users, organizations CASCADE"
            )
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
        gatc_eligible_category_ids: list[int] | None = None,
        **kw: object,
    ) -> User:
        org = None
        if role in (Role.BUSINESS, Role.GATC):
            org = Organization(
                type=OrgType.GATC if role == Role.GATC else OrgType.BUSINESS,
                name=f"Org {uuid.uuid4().hex[:6]}",
                state_code=org_state,
                district_code=org_district,
                # Spec 15: only meaningful (and only ever set here) for role=GATC.
                gatc_eligible_category_ids=(
                    gatc_eligible_category_ids if role == Role.GATC else None
                ),
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


# Smallest byte strings that pass magic-byte sniffing.
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
def storage() -> MemoryStorage:
    s = get_storage()
    assert isinstance(s, MemoryStorage)
    return s


@pytest.fixture
def email() -> MemoryEmail:
    e = get_email()
    assert isinstance(e, MemoryEmail)
    return e


def upload(
    client: TestClient,
    owner: User,
    application_id: object,
    document_type: str = "PROOF_OF_OWNERSHIP",
    data: bytes = PDF_BYTES,
    filename: str = "invoice.pdf",
    content_type: str = "application/pdf",
):  # noqa: ANN201
    return client.post(
        "/api/documents",
        data={"application_id": str(application_id), "document_type": document_type},
        files={"file": (filename, data, content_type)},
        headers=auth_header(owner),
    )


@pytest.fixture
def make_application(make_user, make_instrument) -> Callable[..., Application]:  # noqa: ANN001
    """Creates an application through the services and advances it to `status`."""
    from app.core.application_types import ApplicationStatus as S  # noqa: N817
    from app.schemas.application import ApplicationCreate, StatusChange
    from app.services import applications as app_service
    from app.services import documents as doc_service

    def _make(
        owner: User | None = None,
        instrument: Instrument | None = None,
        *,
        application_type: str = "VERIFICATION",
        status: str = "DRAFT",
        officer: User | None = None,
    ) -> Application:
        owner = owner or make_user(Role.BUSINESS)
        instrument = instrument or make_instrument(owner)
        with SessionLocal() as s:
            user = s.get(User, owner.id)
            application = app_service.create(
                s,
                user,
                ApplicationCreate(instrument_id=instrument.id, application_type=application_type),
                ip="test",
            )
            target = S(status)
            if target == S.DRAFT:
                return application
            required = (
                ["PROOF_OF_OWNERSHIP", "INSTRUMENT_PHOTO"]
                if application_type == "VERIFICATION"
                else ["INSTRUMENT_PHOTO", "PREVIOUS_CERTIFICATE"]
            )
            for kind in required:
                doc_service.upload(
                    s,
                    user,
                    application_id=application.id,
                    document_type=kind,
                    filename=f"{kind.lower()}.pdf",
                    data=PDF_BYTES,
                    ip="test",
                )
            app_service.transition(
                s, user, application.id, StatusChange(status=S.SUBMITTED), ip="test"
            )
            if target == S.SUBMITTED:
                return app_service.load(s, user, application.id)
            reviewer = s.get(User, (officer or make_user(Role.LM_OFFICER)).id)
            app_service.transition(
                s, reviewer, application.id, StatusChange(status=S.DOCUMENT_REVIEW), ip="test"
            )
            if target == S.REJECTED:
                app_service.transition(
                    s,
                    reviewer,
                    application.id,
                    StatusChange(status=S.REJECTED, note="Invoice is not legible"),
                    ip="test",
                )
            elif target == S.DOCUMENTS_DEFICIENT:
                app_service.transition(
                    s,
                    reviewer,
                    application.id,
                    StatusChange(
                        status=S.DOCUMENTS_DEFICIENT, note="Previous certificate photo unreadable"
                    ),
                    ip="test",
                )
            elif target in (S.SCHEDULED, S.INSPECTION, S.APPROVED):
                from app.core import clock
                from app.schemas.application import ReviewChecklistItemUpdate, ReviewChecklistUpdate

                # Step 11: SCHEDULED is gated on every review-checklist item being checked.
                app_service.patch_review_checklist(
                    s,
                    reviewer,
                    application.id,
                    ReviewChecklistUpdate(
                        items=[
                            ReviewChecklistItemUpdate(item_key=i.item_key, checked=True)
                            for i in app_service.review_checklist_items(s, application.id)
                        ]
                    ),
                    ip="test",
                )
                app_service.transition(
                    s,
                    reviewer,
                    application.id,
                    StatusChange(status=S.SCHEDULED, scheduled_date=clock.today()),
                    ip="test",
                )
                if target in (S.INSPECTION, S.APPROVED):
                    # The assigned officer is always `reviewer` (self-assign, spec 05 D2), so
                    # `officer` must be the one starting it too (spec 06 D1).
                    app_service.transition(
                        s, reviewer, application.id, StatusChange(status=S.INSPECTION), ip="test"
                    )
                if target == S.APPROVED:
                    from app.schemas.inspection import (
                        ChecklistItemUpdate,
                        InspectionUpdate,
                        MeasurementUpdate,
                    )
                    from app.services import inspections as inspections_service

                    inspection_id = app_service.load(s, user, application.id).inspection.id
                    detail = inspections_service.detail(s, reviewer, inspection_id)
                    inspections_service.patch(
                        s,
                        reviewer,
                        inspection_id,
                        InspectionUpdate(
                            checklist_items=[
                                ChecklistItemUpdate(item_key=i.item_key, result="PASS")
                                for i in detail.checklist_items
                            ],
                            measurements=[
                                MeasurementUpdate(
                                    label=m.label, observed_value=str(m.expected_value)
                                )
                                for m in detail.measurements
                            ],
                        ),
                    )
                    inspections_service.submit(s, reviewer, inspection_id, ip="test")
                    # Any in-scope officer may approve (spec 07 D1), not just `reviewer`.
                    app_service.transition(
                        s, reviewer, application.id, StatusChange(status=S.APPROVED), ip="test"
                    )
            elif target != S.DOCUMENT_REVIEW:
                raise ValueError(f"factory can't reach {status}")
            return app_service.load(s, user, application.id)

    return _make
