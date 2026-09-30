"""transportability and verification mode

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A brand-new enum type (unlike 0005/0008's `ALTER TYPE ... ADD VALUE` on an *existing* type),
# added via `ADD COLUMN` on an *existing* table (unlike 0001-0003's new enum types, which were
# all created implicitly as part of `CREATE TABLE`). SQLAlchemy only auto-issues `CREATE TYPE`
# as a DDL event attached to `Table.create()`; a bare `op.add_column` does not trigger it, so the
# type must be created explicitly first. No transactional gotcha here either way: `CREATE TYPE`
# (unlike `ALTER TYPE ... ADD VALUE`) is fully transactional in Postgres, so this can all still go
# in one migration/transaction.
VERIFICATION_MODE = sa.Enum("OFFICE_TEST_CENTRE", "ON_SITE", name="verification_mode")


def upgrade() -> None:
    """Upgrade schema."""
    # instruments.transportable: added nullable with a server default, backfilled, then set
    # NOT NULL — the standard 3-step "safe add-a-required-column" sequence for an existing table
    # (avoids ever requiring a NOT NULL constraint to be validated against a column that might
    # still contain NULLs). In Postgres 11+, ADD COLUMN ... DEFAULT true on its own is already a
    # metadata-only change (no table rewrite, existing rows read the default via the catalog's
    # "missing value" optimization) but the explicit UPDATE below is kept anyway for auditability
    # and so this migration doesn't rely on that optimization to guarantee non-null data.
    op.add_column(
        "instruments",
        sa.Column("transportable", sa.Boolean(), server_default=sa.true(), nullable=True),
    )
    op.execute("UPDATE instruments SET transportable = true WHERE transportable IS NULL")
    op.alter_column("instruments", "transportable", nullable=False)

    # applications.verification_mode: nullable, no backfill. Unlike transportable above, this is
    # a *snapshot* (spec 14 §1) — the whole point is that it reflects instrument.transportable at
    # the moment each application was created, which can't be reconstructed for applications that
    # already existed before this migration. They keep verification_mode = NULL permanently;
    # every application created from here on always gets one (services/applications.py: create()).
    VERIFICATION_MODE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "applications",
        sa.Column("verification_mode", VERIFICATION_MODE, nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("applications", "verification_mode")
    VERIFICATION_MODE.drop(op.get_bind(), checkfirst=True)

    op.drop_column("instruments", "transportable")
