"""certificate reminders

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30 14:36:00.467394

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("certificates", sa.Column("reminder_30d_sent_at", sa.Date(), nullable=True))
    op.add_column("certificates", sa.Column("reminder_7d_sent_at", sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("certificates", "reminder_7d_sent_at")
    op.drop_column("certificates", "reminder_30d_sent_at")
