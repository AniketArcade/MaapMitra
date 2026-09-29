"""Admin CLI.

python -m app.cli create-superadmin --email admin@example.com
python -m app.cli create-bucket
"""

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
            actor=None,
            action="USER_CREATED",
            entity_type="user",
            entity_id=user.id,
            details={"role": Role.SUPER_ADMIN.value, "via": "cli"},
        )
        db.commit()
    print(f"Created SUPER_ADMIN {email}")
    return 0


def create_bucket() -> int:
    from app.core.application_types import ALLOWED_CONTENT_TYPES, MAX_FILE_BYTES
    from app.storage import SupabaseStorage, get_storage

    storage = get_storage()
    if not isinstance(storage, SupabaseStorage):
        print("STORAGE_BACKEND is not 'supabase'; nothing to create.", file=sys.stderr)
        return 1
    created = storage.ensure_bucket(
        file_size_limit=MAX_FILE_BYTES, allowed_mime_types=list(ALLOWED_CONTENT_TYPES)
    )
    if created:
        print(f"Created private bucket '{storage.bucket}'")
    else:
        print(f"Private bucket '{storage.bucket}' already exists")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Super Admin")
    sub.add_parser("create-bucket", help="create the private documents bucket if missing")
    args = parser.parse_args()
    if args.command == "create-superadmin":
        return create_superadmin(args.email, args.name)
    if args.command == "create-bucket":
        return create_bucket()
    return 1


if __name__ == "__main__":
    sys.exit(main())
