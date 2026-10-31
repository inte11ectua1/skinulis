"""Financial storage; aggregate and authorization rules belong to later services."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_expenses"),
        CheckConstraint("id > 0", name="ck_expenses_id_positive"),
        CheckConstraint("version > 0", name="ck_expenses_version"),
        CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name="ck_expenses_title"
        ),
        CheckConstraint(
            "split_mode IN ('equal', 'custom', 'by_items')",
            name="ck_expenses_split_mode",
        ),
        CheckConstraint(
            "amount_kopecks BETWEEN 1 AND 100000000", name="ck_expenses_amount"
        ),
        CheckConstraint(
            "deleted_at IS NULL OR deleted_at >= created_at",
            name="ck_expenses_deleted_at",
        ),
        UniqueConstraint("group_id", "client_request_id", name="uq_expenses_request"),
        UniqueConstraint("id", "group_id", name="uq_expenses_id_group"),
        ForeignKeyConstraint(
            ["group_id", "payer_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_expenses_payer_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_expenses_group_created", "group_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", name="fk_expenses_group", ondelete="RESTRICT"),
    )
    payer_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(120))
    split_mode: Mapped[str] = mapped_column(String(8))
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    client_request_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_create_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    initial_create_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(BigInteger, server_default="1")

    @validates("initial_create_intent", "initial_create_result")
    def immutable_create_history(
        self, key: str, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        previous = getattr(self, key, None)
        if previous is not None and previous != value:
            raise ValueError("Original expense creation history is immutable")
        return value


class ExpenseItem(Base):
    __tablename__ = "expense_items"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_expense_items"),
        CheckConstraint("id > 0", name="ck_expense_items_id_positive"),
        CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120", name="ck_expense_items_title"
        ),
        CheckConstraint("amount_kopecks > 0", name="ck_expense_items_amount"),
        CheckConstraint("position BETWEEN 1 AND 50", name="ck_expense_items_position"),
        UniqueConstraint("expense_id", "position", name="uq_expense_items_position"),
        UniqueConstraint(
            "id", "expense_id", "group_id", name="uq_expense_items_parent"
        ),
        ForeignKeyConstraint(
            ["expense_id", "group_id"],
            ["expenses.id", "expenses.group_id"],
            name="fk_expense_items_expense",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    expense_id: Mapped[int] = mapped_column(BigInteger)
    group_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(120))
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(SmallInteger)


class ExpenseShare(Base):
    __tablename__ = "expense_shares"
    __table_args__ = (
        PrimaryKeyConstraint("expense_id", "user_id", name="pk_expense_shares"),
        CheckConstraint("amount_kopecks >= 0", name="ck_expense_shares_amount"),
        ForeignKeyConstraint(
            ["expense_id", "group_id"],
            ["expenses.id", "expenses.group_id"],
            name="fk_expense_shares_expense",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["group_id", "user_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_expense_shares_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_expense_shares_member", "group_id", "user_id", "expense_id"),
    )

    expense_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    group_id: Mapped[int] = mapped_column(BigInteger)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)


class ExpenseItemShare(Base):
    __tablename__ = "expense_item_shares"
    __table_args__ = (
        PrimaryKeyConstraint("item_id", "user_id", name="pk_expense_item_shares"),
        CheckConstraint("amount_kopecks >= 0", name="ck_expense_item_shares_amount"),
        ForeignKeyConstraint(
            ["item_id", "expense_id", "group_id"],
            ["expense_items.id", "expense_items.expense_id", "expense_items.group_id"],
            name="fk_expense_item_shares_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["expense_id", "user_id"],
            ["expense_shares.expense_id", "expense_shares.user_id"],
            name="fk_expense_item_shares_final_share",
            ondelete="RESTRICT",
        ),
        Index("ix_expense_item_shares_final", "expense_id", "user_id"),
    )

    item_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    expense_id: Mapped[int] = mapped_column(BigInteger)
    group_id: Mapped[int] = mapped_column(BigInteger)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_settlements"),
        CheckConstraint("id > 0", name="ck_settlements_id_positive"),
        CheckConstraint("amount_kopecks > 0", name="ck_settlements_amount"),
        CheckConstraint("sender_id <> receiver_id", name="ck_settlements_parties"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected', 'cancelled')",
            name="ck_settlements_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR "
            "(status IN ('confirmed', 'rejected', 'cancelled') "
            "AND resolved_at IS NOT NULL AND resolved_at >= created_at)",
            name="ck_settlements_resolved_at",
        ),
        UniqueConstraint(
            "group_id", "client_request_id", name="uq_settlements_request"
        ),
        ForeignKeyConstraint(
            ["group_id", "sender_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_sender_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["group_id", "receiver_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_settlements_receiver_membership",
            ondelete="RESTRICT",
        ),
        Index("ix_settlements_group_created", "group_id", "created_at", "id"),
        Index(
            "ix_settlements_receiver_status",
            "receiver_id",
            "status",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", name="fk_settlements_group", ondelete="RESTRICT"),
    )
    sender_id: Mapped[int] = mapped_column(BigInteger)
    receiver_id: Mapped[int] = mapped_column(BigInteger)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(9), server_default="pending")
    notification_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    client_request_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
