"""Add financial storage after the merged identity schema.

Revision ID: 0004_financial_domain
Revises: 0003_groups_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_financial_domain"
down_revision: str | None = "0003_groups_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("payer_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("split_mode", sa.String(length=8), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "split_mode IN ('equal', 'custom', 'by_items')",
            name="ck_expenses_split_mode",
        ),
        sa.CheckConstraint(
            "amount_kopecks BETWEEN 1 AND 100000000", name="ck_expenses_amount"
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name="ck_expenses_title"
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR deleted_at >= created_at",
            name="ck_expenses_deleted_at",
        ),
        sa.CheckConstraint("id > 0", name="ck_expenses_id_positive"),
        sa.ForeignKeyConstraint(
            ["group_id", "payer_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_expenses_payer_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name="fk_expenses_group", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_expenses"),
        sa.UniqueConstraint(
            "group_id", "client_request_id", name="uq_expenses_request"
        ),
        sa.UniqueConstraint("id", "group_id", name="uq_expenses_id_group"),
    )
    op.create_index(
        "ix_expenses_group_created",
        "expenses",
        ["group_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "expense_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("expense_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("amount_kopecks > 0", name="ck_expense_items_amount"),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name="ck_expense_items_title"
        ),
        sa.CheckConstraint("id > 0", name="ck_expense_items_id_positive"),
        sa.CheckConstraint(
            "position BETWEEN 1 AND 50", name="ck_expense_items_position"
        ),
        sa.ForeignKeyConstraint(
            ["expense_id", "group_id"],
            ["expenses.id", "expenses.group_id"],
            name="fk_expense_items_expense",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_expense_items"),
        sa.UniqueConstraint("expense_id", "position", name="uq_expense_items_position"),
        sa.UniqueConstraint(
            "id", "expense_id", "group_id", name="uq_expense_items_parent"
        ),
    )
    op.create_table(
        "expense_shares",
        sa.Column("expense_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("amount_kopecks >= 0", name="ck_expense_shares_amount"),
        sa.ForeignKeyConstraint(
            ["expense_id", "group_id"],
            ["expenses.id", "expenses.group_id"],
            name="fk_expense_shares_expense",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id", "user_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_expense_shares_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("expense_id", "user_id", name="pk_expense_shares"),
    )
    op.create_index(
        "ix_expense_shares_member",
        "expense_shares",
        ["group_id", "user_id", "expense_id"],
        unique=False,
    )
    op.create_table(
        "expense_item_shares",
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("expense_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("amount_kopecks >= 0", name="ck_expense_item_shares_amount"),
        sa.ForeignKeyConstraint(
            ["expense_id", "user_id"],
            ["expense_shares.expense_id", "expense_shares.user_id"],
            name="fk_expense_item_shares_final_share",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "expense_id", "group_id"],
            ["expense_items.id", "expense_items.expense_id", "expense_items.group_id"],
            name="fk_expense_item_shares_item",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("item_id", "user_id", name="pk_expense_item_shares"),
    )
    op.create_index(
        "ix_expense_item_shares_final",
        "expense_item_shares",
        ["expense_id", "user_id"],
        unique=False,
    )
    op.create_table(
        "settlements",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("receiver_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_kopecks", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=9), server_default="pending", nullable=False
        ),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR (status IN ('confirmed', 'rejected', 'cancelled') AND resolved_at IS NOT NULL AND resolved_at >= created_at)",
            name="ck_settlements_resolved_at",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected', 'cancelled')",
            name="ck_settlements_status",
        ),
        sa.CheckConstraint("amount_kopecks > 0", name="ck_settlements_amount"),
        sa.CheckConstraint("id > 0", name="ck_settlements_id_positive"),
        sa.CheckConstraint("sender_id <> receiver_id", name="ck_settlements_parties"),
        sa.ForeignKeyConstraint(
            ["group_id", "receiver_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_receiver_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id", "sender_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_sender_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name="fk_settlements_group",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_settlements"),
        sa.UniqueConstraint(
            "group_id", "client_request_id", name="uq_settlements_request"
        ),
    )
    op.create_index(
        "ix_settlements_group_created",
        "settlements",
        ["group_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_settlements_receiver_status",
        "settlements",
        ["receiver_id", "status", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("settlements")
    op.drop_table("expense_item_shares")
    op.drop_table("expense_shares")
    op.drop_table("expense_items")
    op.drop_table("expenses")
