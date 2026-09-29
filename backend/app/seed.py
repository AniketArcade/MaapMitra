"""Demo seed data. Usage: python -m app.seed --password '<demo password>'

Idempotent: existing emails and organizations are skipped. See database/seed/README.md.
PRODUCTION SHORTCUT: delete these accounts after the hackathon.
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import OrgType, Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.user import User

ORGS = [
    {"name": "ABC Traders", "state_code": "JH", "district_code": "DHN"},
    # Second business, used to demo and test org isolation.
    {"name": "Other Traders", "state_code": "JH", "district_code": "DHN"},
]

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
    return created


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
