"""Optional display names for existing and new identities; no data rewrite."""

import sqlalchemy as sa

from alembic import op

revision = "0007_user_display_name"
down_revision = "0006_settlement_notification_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_users_display_name",
        "users",
        "display_name IS NULL OR (length(display_name) BETWEEN 1 AND 64 AND display_name = btrim(display_name) AND display_name !~ '[[:cntrl:]]')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_display_name", "users", type_="check")
    op.drop_column("users", "display_name")
