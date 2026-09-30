"""certificate superseding

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-30 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Hand-written: autogenerate does not diff enum *values*, only enum existence. Same pattern as
    # 0005/0008 (ALTER TYPE ... ADD VALUE on an *existing* type, safe inside this migration's
    # transaction as long as the new value is never *used* — inserted, defaulted, or compared —
    # within the same transaction). The two ADD COLUMN statements below reference
    # certificates.id, never certificate_status, so that holds here too.
    # IF NOT EXISTS: the value survives `downgrade -1` (Postgres can't drop a single enum value,
    # see downgrade() below), so a repeat `upgrade head` must not fail on it.
    op.execute("ALTER TYPE certificate_status ADD VALUE IF NOT EXISTS 'SUPERSEDED'")

    # Self-referential FKs, both nullable and ON DELETE SET NULL: a certificate is never
    # hard-deleted by this relationship (nothing in this codebase hard-deletes a certificate at
    # all today, but the FK shouldn't assume that forever). Added via add_column + a named
    # create_foreign_key, mirroring 0005's `inspections.submitted_by` pattern (a bare add_column
    # doesn't auto-issue an FK the way Table.create() would).
    op.add_column("certificates", sa.Column("supersedes_certificate_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_certificates_supersedes_certificate_id_certificates"),
        "certificates",
        "certificates",
        ["supersedes_certificate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "certificates", sa.Column("superseded_by_certificate_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_certificates_superseded_by_certificate_id_certificates"),
        "certificates",
        "certificates",
        ["superseded_by_certificate_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_certificates_superseded_by_certificate_id_certificates"),
        "certificates",
        type_="foreignkey",
    )
    op.drop_column("certificates", "superseded_by_certificate_id")
    op.drop_constraint(
        op.f("fk_certificates_supersedes_certificate_id_certificates"),
        "certificates",
        type_="foreignkey",
    )
    op.drop_column("certificates", "supersedes_certificate_id")
    # Postgres cannot drop a single enum value (no ALTER TYPE ... DROP VALUE). Recreating
    # certificate_status without SUPERSEDED would require rewriting every dependent column
    # (certificates.status) and is out of scope for an MVP downgrade path: the value is left in
    # place, same documented limitation as 0005's/0008's own downgrades. `downgrade -1` after this
    # revision does not fully reverse the enum change.
