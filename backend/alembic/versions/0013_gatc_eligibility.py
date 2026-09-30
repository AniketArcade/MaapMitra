"""gatc eligibility and inspection assignee role

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-01 12:00:00.000000

Spec 15 (`docs/specs/15-gatc-eligibility.md`). Makes GATC routing real (still deliberately
minimal, per the root CLAUDE.md's now-resolved "GATC workflow depth" decision), reusing the
existing inspection/checklist/measurement/approve-reject machinery entirely rather than building
a parallel GATC-specific workflow.

Two independent, additive changes, in one migration/transaction:

1. `organizations.gatc_eligible_category_ids` (nullable JSONB array of `instrument_categories.id`
   values): which categories a GATC organization is approved to test. No table create, no enum —
   a plain `ADD COLUMN`, nullable forever (no backfill needed: every existing organization simply
   has no GATC eligibility configured yet, which is exactly what NULL means).
2. `inspections.assignee_role` (new `inspection_assignee_role` enum type, NOT NULL): which of the
   two roles capable of running an inspection (LM_OFFICER or GATC) was actually assigned. Added
   nullable with a server default, backfilled, then set NOT NULL — the same 3-step sequence
   `0009_transportability` uses for `instruments.transportable`. Unlike that column's boolean
   default (an *assumption* about pre-existing rows), this backfill is a *known fact*: every
   Inspection row that exists before this migration was created by the pre-spec-15 code path in
   `services/applications.py: transition()`, which unconditionally self-assigned the scheduling
   officer and only ever let LM_OFFICER reach that transition (`ALLOWED_TRANSITIONS[(DOCUMENT_
   REVIEW, SCHEDULED)]` was `Edge(frozenset({Role.LM_OFFICER}), enabled=True)` with no GATC route
   before this step) — so `LM_OFFICER` is not a guess here, it is what every existing row already
   is. The enum type follows this codebase's existing convention for small closed-value columns
   (a real Postgres `Enum`, like `ChecklistResult`/`VerificationMode`/`PaymentStatus`, not a
   CHECK-constrained Text column), added via `ADD COLUMN` on an existing table exactly like
   `0009_transportability`'s own `verification_mode` (a brand-new type needs an explicit
   `CREATE TYPE`; SQLAlchemy only auto-issues one as part of `Table.create()`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INSPECTION_ASSIGNEE_ROLE = sa.Enum("LM_OFFICER", "GATC", name="inspection_assignee_role")


def upgrade() -> None:
    """Upgrade schema."""
    # organizations.gatc_eligible_category_ids: nullable, no backfill needed — NULL is the
    # correct, permanent value for every organization that hasn't been configured for GATC
    # category eligibility (which, before this step, is all of them).
    op.add_column(
        "organizations",
        sa.Column(
            "gatc_eligible_category_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_check_constraint(
        "gatc_eligible_only_for_gatc_org",
        "organizations",
        "gatc_eligible_category_ids IS NULL OR type = 'GATC'",
    )

    # inspections.assignee_role: added nullable with a server default, backfilled, then set NOT
    # NULL (mirrors 0009_transportability's own 3-step sequence for instruments.transportable).
    INSPECTION_ASSIGNEE_ROLE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "inspections",
        sa.Column(
            "assignee_role",
            INSPECTION_ASSIGNEE_ROLE,
            server_default="LM_OFFICER",
            nullable=True,
        ),
    )
    op.execute("UPDATE inspections SET assignee_role = 'LM_OFFICER' WHERE assignee_role IS NULL")
    op.alter_column("inspections", "assignee_role", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("inspections", "assignee_role")
    INSPECTION_ASSIGNEE_ROLE.drop(op.get_bind(), checkfirst=True)

    op.drop_constraint("gatc_eligible_only_for_gatc_org", "organizations", type_="check")
    op.drop_column("organizations", "gatc_eligible_category_ids")
