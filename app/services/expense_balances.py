"""Read-only mutation-envelope aggregation, approved in #36; no O-06 endpoints."""

from sqlalchemy import Numeric, cast, func, select, union_all
from sqlalchemy.orm import Session

from app.models import Expense, ExpenseShare, GroupMember, Settlement
from app.schemas.expenses import BalanceProfile
from app.services.expenses import ExpenseSnapshotInvalid
from app.services.money import format_money


def mutation_balances(session: Session, group_id: int) -> list[BalanceProfile] | None:
    if (
        session.scalar(
            select(Settlement.id)
            .where(Settlement.group_id == group_id, Settlement.status == "confirmed")
            .limit(1)
        )
        is None
    ):
        return None
    # Ordinary SQL CHECK cannot guarantee the cross-row snapshot invariant.
    snapshots = session.execute(
        select(
            Expense.amount_kopecks,
            func.count(ExpenseShare.user_id),
            func.sum(ExpenseShare.amount_kopecks),
        )
        .outerjoin(ExpenseShare, ExpenseShare.expense_id == Expense.id)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .group_by(Expense.id, Expense.amount_kopecks)
    )
    for amount, count, total in snapshots:
        if count == 0 or total != amount:
            raise ExpenseSnapshotInvalid("Stored expense snapshot is inconsistent")
    members = list(
        session.scalars(
            select(GroupMember.user_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.user_id)
        )
    )
    balances = dict.fromkeys(members, 0)
    # Cast BEFORE unary arithmetic; SUM(bigint) itself is exact NUMERIC as well.
    entries = union_all(
        select(
            Expense.payer_id.label("user_id"),
            cast(Expense.amount_kopecks, Numeric).label("delta"),
        ).where(Expense.group_id == group_id, Expense.deleted_at.is_(None)),
        select(ExpenseShare.user_id, -cast(ExpenseShare.amount_kopecks, Numeric))
        .join(Expense, Expense.id == ExpenseShare.expense_id)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None)),
        select(Settlement.sender_id, cast(Settlement.amount_kopecks, Numeric)).where(
            Settlement.group_id == group_id, Settlement.status == "confirmed"
        ),
        select(Settlement.receiver_id, -cast(Settlement.amount_kopecks, Numeric)).where(
            Settlement.group_id == group_id, Settlement.status == "confirmed"
        ),
    ).subquery()
    for user_id, total in session.execute(
        select(entries.c.user_id, func.sum(entries.c.delta)).group_by(entries.c.user_id)
    ):
        if user_id not in balances:
            raise ExpenseSnapshotInvalid("Invalid financial membership")
        balances[user_id] = int(total)
    if sum(balances.values()) != 0:
        raise ExpenseSnapshotInvalid("Unbalanced financial history")
    return [
        BalanceProfile(user_id=user_id, balance=format_money(amount))
        for user_id, amount in balances.items()
    ]
