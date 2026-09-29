"""Demo seed data. Usage: python -m app.seed --password '<demo password>'

Idempotent: existing emails and organizations are skipped. See database/seed/README.md.
PRODUCTION SHORTCUT: delete these accounts after the hackathon.
"""

import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.application_types import ApplicationStatus, ApplicationType, DocumentType
from app.core.config import get_settings
from app.core.roles import OrgType, Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.application import Application
from app.models.instrument import Instrument
from app.models.organization import Organization
from app.models.user import User
from app.schemas.application import ApplicationCreate, StatusChange
from app.schemas.instrument import InstrumentCreate
from app.seed_files import demo_pdf, demo_png
from app.services import applications as applications_service
from app.services import documents as documents_service
from app.services import instruments as instruments_service

ORGS = [
    {"name": "ABC Traders", "state_code": "JH", "district_code": "DHN"},
    # Second business, used to demo and test org isolation.
    {"name": "Other Traders", "state_code": "JH", "district_code": "DHN"},
]

DEMO_INSTRUMENT = {
    "instrument_type": "WEIGHING_SCALE",
    "manufacturer": "Demo Scales",
    "model": "DS-30",
    "serial_number": "OTH-0001",
    "capacity": 30,
    "capacity_unit": "kg",
    "address": "Other Traders shop, Dhanbad",
    "state_code": "JH",
    "district_code": "DHN",
}

USERS = [
    {"email": "admin@lm.demo", "full_name": "Demo Super Admin", "role": Role.SUPER_ADMIN},
    {
        "email": "state.jh@lm.demo",
        "full_name": "Jharkhand State Admin",
        "role": Role.STATE_ADMIN,
        "state_code": "JH",
    },
    {
        "email": "district.dhn@lm.demo",
        "full_name": "Dhanbad District Admin",
        "role": Role.DISTRICT_ADMIN,
        "state_code": "JH",
        "district_code": "DHN",
    },
    {
        "email": "officer.dhn@lm.demo",
        "full_name": "Dhanbad LM Officer",
        "role": Role.LM_OFFICER,
        "state_code": "JH",
        "district_code": "DHN",
    },
    {
        "email": "owner@abctraders.demo",
        "full_name": "ABC Traders Owner",
        "role": Role.BUSINESS,
        "org": "ABC Traders",
    },
    {
        "email": "owner@othertraders.demo",
        "full_name": "Other Traders Owner",
        "role": Role.BUSINESS,
        "org": "Other Traders",
    },
]


def seed(db: Session, password: str) -> list[str]:
    created: list[str] = []
    orgs: dict[str, Organization] = {}
    for spec in ORGS:
        org = db.scalar(select(Organization).where(Organization.name == spec["name"]))
        if org is None:
            org = Organization(type=OrgType.BUSINESS, **spec)
            db.add(org)
            created.append(f"org {spec['name']}")
        orgs[spec["name"]] = org
    db.flush()

    password_hash = hash_password(password)
    for spec in USERS:
        if db.scalar(select(User).where(User.email == spec["email"])):
            continue
        org_name = spec.get("org")
        db.add(
            User(
                email=spec["email"],
                full_name=spec["full_name"],
                role=spec["role"],
                password_hash=password_hash,
                organization=orgs[org_name] if org_name else None,
                state_code=spec.get("state_code"),
                district_code=spec.get("district_code"),
            )
        )
        created.append(f"user {spec['email']}")
    db.commit()

    # Other Traders' instrument, used to demo org isolation. XYZ12345 is registered live
    # by ABC Traders during the demo, so it is deliberately NOT seeded.
    owner = db.scalar(select(User).where(User.email == "owner@othertraders.demo"))
    exists = db.scalar(
        select(Instrument).where(
            func.lower(Instrument.manufacturer) == DEMO_INSTRUMENT["manufacturer"].lower(),
            Instrument.serial_number == DEMO_INSTRUMENT["serial_number"],
        )
    )
    if owner is not None and exists is None:
        body = InstrumentCreate.model_validate(DEMO_INSTRUMENT)
        exists = instruments_service.create(db, owner, body, ip="seed")
        created.append(f"instrument {exists.serial_number} ({exists.instrument_uid})")

    # A SUBMITTED application for OTH-0001, so the officer has a queue item on first login.
    # ABC Traders' application is NOT seeded: the demo creates it live.
    if owner is not None and exists is not None:
        has_application = db.scalar(
            select(Application.id).where(Application.instrument_id == exists.id).limit(1)
        )
        if has_application is None:
            created.append(_seed_application(db, owner, exists))
    return created


def _seed_application(db: Session, owner: User, instrument: Instrument) -> str:
    application = applications_service.create(
        db,
        owner,
        ApplicationCreate(
            instrument_id=instrument.id, application_type=ApplicationType.VERIFICATION
        ),
        ip="seed",
    )
    files = (
        (
            DocumentType.PROOF_OF_OWNERSHIP,
            "invoice-oth-0001.pdf",
            demo_pdf("Demo invoice OTH-0001"),
        ),
        (DocumentType.INSTRUMENT_PHOTO, "nameplate-oth-0001.png", demo_png()),
    )
    for document_type, filename, data in files:
        documents_service.upload(
            db,
            owner,
            application_id=application.id,
            document_type=document_type,
            filename=filename,
            data=data,
            ip="seed",
        )
    applications_service.transition(
        db, owner, application.id, StatusChange(status=ApplicationStatus.SUBMITTED), ip="seed"
    )
    return f"application {application.application_number} (SUBMITTED, 2 documents)"


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed")
    parser.add_argument("--password", required=True, help="shared demo password (min 8 chars)")
    parser.add_argument("--force-demo", action="store_true", help="allow when ENV=production")
    args = parser.parse_args()

    if get_settings().ENV == "production" and not args.force_demo:
        print(
            "Refusing to seed demo users when ENV=production (use --force-demo).", file=sys.stderr
        )
        return 1
    if len(args.password) < 8:
        print("Demo password must be at least 8 characters.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        created = seed(db, args.password)
    print("\n".join(created) if created else "Nothing to do: demo data already present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
