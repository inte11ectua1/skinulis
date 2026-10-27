"""groups and Telegram identity"""

import sqlalchemy as sa

from alembic import op

revision: str = "0003_groups_identity"
down_revision: str | None = "0002_users"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id > 0", name="ck_groups_id_positive"),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 120", name="ck_groups_name_length"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_groups_owner", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_groups"),
        sa.UniqueConstraint("owner_id", "client_request_id", name="uq_groups_request"),
    )
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at = created_at + interval '10 minutes'",
            name="ck_telegram_link_codes_ttl",
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name="ck_telegram_link_codes_hash"
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (revoked_at IS NULL AND consumed_at >= created_at AND consumed_at < expires_at)",
            name="ck_telegram_link_codes_consumed_time",
        ),
        sa.CheckConstraint("id > 0", name="ck_telegram_link_codes_id_positive"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_telegram_link_codes_revoked_time",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_telegram_link_codes_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_telegram_link_codes"),
        sa.UniqueConstraint("token_hash", name="uq_telegram_link_codes_hash"),
    )
    op.create_index(
        "ix_telegram_link_codes_user", "telegram_link_codes", ["user_id"], unique=False
    )
    op.create_table(
        "group_invites",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by", sa.BigInteger(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at = created_at + interval '24 hours'", name="ck_group_invites_ttl"
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name="ck_group_invites_hash"
        ),
        sa.CheckConstraint(
            "(consumed_at IS NULL) = (consumed_by IS NULL)",
            name="ck_group_invites_consumption",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (revoked_at IS NULL AND consumed_at >= created_at AND consumed_at < expires_at)",
            name="ck_group_invites_consumed_time",
        ),
        sa.CheckConstraint("id > 0", name="ck_group_invites_id_positive"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_group_invites_revoked_time",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by"],
            ["users.id"],
            name="fk_group_invites_consumer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_group_invites_group",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_group_invites"),
        sa.UniqueConstraint(
            "group_id", "client_request_id", name="uq_group_invites_request"
        ),
        sa.UniqueConstraint("token_hash", name="uq_group_invites_hash"),
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("slot BETWEEN 1 AND 30", name="ck_group_members_slot"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_group_members_group",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_group_members_user", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("group_id", "user_id", name="pk_group_members"),
        sa.UniqueConstraint("group_id", "slot", name="uq_group_members_slot"),
    )
    op.create_index(
        "ix_group_members_user_group",
        "group_members",
        ["user_id", "group_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_groups_owner_membership",
        "groups",
        "group_members",
        ["id", "owner_id"],
        ["group_id", "user_id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_foreign_key(
        "fk_group_invites_consumer_membership",
        "group_invites",
        "group_members",
        ["group_id", "consumed_by"],
        ["group_id", "user_id"],
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_group_invites_consumer_membership", "group_invites", type_="foreignkey"
    )
    op.drop_constraint("fk_groups_owner_membership", "groups", type_="foreignkey")
    op.drop_index("ix_group_members_user_group", table_name="group_members")
    op.drop_table("group_members")
    op.drop_table("group_invites")
    op.drop_index("ix_telegram_link_codes_user", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
    op.drop_table("groups")
