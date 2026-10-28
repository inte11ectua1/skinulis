"""Keep original POST intent/result and optimistic expense version.

Revision ID: 0005_expense_replay_version
Revises: 0004_financial_domain
Approved: issue #36, comment 6469818682. Legacy history remains unknown (NULL).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_expense_replay_version"
down_revision: str | None = "0004_financial_domain"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("initial_create_intent", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "expenses",
        sa.Column("initial_create_result", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "expenses",
        sa.Column("version", sa.BigInteger(), server_default="1", nullable=False),
    )
    op.create_check_constraint("ck_expenses_version", "expenses", "version > 0")


def downgrade() -> None:
    op.drop_constraint("ck_expenses_version", "expenses", type_="check")
    op.drop_column("expenses", "version")
    op.drop_column("expenses", "initial_create_result")
    op.drop_column("expenses", "initial_create_intent")
