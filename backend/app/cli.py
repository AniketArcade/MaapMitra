"""Admin CLI.  Usage: python -m app.cli create-superadmin --email admin@example.com"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.roles import Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.services import audit


def create_superadmin(email: str, full_name: str) -> int:
    email = email.strip().lower()
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8 or len(password) > 128:
        print("Password must be 8-128 characters.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            print(f"User {email} already exists.", file=sys.stderr)
            return 1
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=Role.SUPER_ADMIN,
        )
        db.add(user)
        db.flush()
        audit.log(
            db,
            action="USER_CREATED",
            entity_type="user",
            entity_id=user.id,
            details={"role": Role.SUPER_ADMIN.value, "via": "cli"},
        )
        db.commit()
    print(f"Created SUPER_ADMIN {email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Super Admin")
    args = parser.parse_args()
    if args.command == "create-superadmin":
        return create_superadmin(args.email, args.name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
