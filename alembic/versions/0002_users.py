"""Shared users identity; no groups or financial tables (T-05)."""

import sqlalchemy as sa

from alembic import op

revision: str = "0002_users"
down_revision: str | None = "0001_baseline"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        sa.CheckConstraint("id > 0", name="ck_users_id_positive"),
        sa.CheckConstraint("telegram_id > 0", name="ck_users_telegram_id_positive"),
        sa.CheckConstraint(
            "email IS NOT NULL OR telegram_id IS NOT NULL",
            name="ck_users_identity_present",
        ),
        sa.CheckConstraint(
            "(email IS NULL) = (password_hash IS NULL)",
            name="ck_users_email_password_pair",
        ),
        sa.CheckConstraint(
            "email IS NULL OR (length(email) BETWEEN 3 AND 254 "
            "AND email = lower(email) AND email = btrim(email) "
            "AND email !~ '[[:space:]]' AND email !~ '[^ -~]')",
            name="ck_users_email_normalized",
        ),
        sa.CheckConstraint(
            "password_hash IS NULL OR password_hash LIKE '$argon2id$%'",
            name="ck_users_password_argon2id",
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
