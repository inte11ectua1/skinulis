"""Durable one-time pending notification permission, with historical backfill."""

import sqlalchemy as sa

from alembic import op

revision: str = "0006_settlement_notification_claim"
down_revision: str | None = "0005_expense_replay_version"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The approved revision ID is 34 characters; Alembic defaults to VARCHAR(32).
    op.alter_column("alembic_version", "version_num", type_=sa.String(64))
    op.add_column(
        "settlements",
        sa.Column("notification_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE settlements SET notification_claimed_at = created_at")


def downgrade() -> None:
    op.drop_column("settlements", "notification_claimed_at")
    # Keep version_num wide: Alembic replaces the current 34-character revision
    # only AFTER downgrade() returns. This metadata width has no domain effect.
