"""Pure split functions; тип ID и ключ порядка предоставляет вызывающий код (Q-02).

Нет default-порядка и выбранного за владельца users типа ID. Примеры с int и
order_key=int-identity проверяют арифметику, а не принимают схему users/API.
"""

from collections.abc import Callable, Collection, Hashable, Sequence
from dataclasses import dataclass

from app.services.money import (
    ContractPendingError,
    validate_amount,
    validate_expense_amount,
)

MAX_GROUP_MEMBERS = 30
MAX_ITEMS = 50
MAX_TITLE_LENGTH = 120


class SplitError(ValueError):
    """Некорректный состав, доли, позиции или неоднозначный явный порядок."""


@dataclass(frozen=True, slots=True)
class ExpenseItem[UserId: Hashable]:
    """Вход одной позиции в копейках; это не ORM/Pydantic/API-схема."""

    title: str
    amount: int
    participants: Sequence[UserId]


def _group[UserId: Hashable](group_members: Collection[UserId]) -> set[UserId]:
    members = tuple(group_members)
    if not 1 <= len(members) <= MAX_GROUP_MEMBERS:
        raise SplitError("Group must contain between 1 and 30 members")
    if any(isinstance(user_id, bool) for user_id in members):
        raise TypeError("Boolean cannot stand in for a user ID")
    unique = set(members)
    if len(unique) != len(members):
        raise SplitError("Group context contains duplicate members")
    return unique


def _ordered[UserId: Hashable](
    participants: Sequence[UserId],
    members: set[UserId],
    order_key: Callable[[UserId], int],
) -> list[UserId]:
    selected = tuple(participants)
    if not 1 <= len(selected) <= MAX_GROUP_MEMBERS:
        raise SplitError("Select between 1 and 30 participants")
    if any(isinstance(user_id, bool) for user_id in selected):
        raise TypeError("Boolean cannot stand in for a user ID")
    if len(set(selected)) != len(selected):
        raise SplitError("Participants must be unique")
    if not set(selected) <= members:
        raise SplitError("Every participant must belong to the group")
    ranked = [(order_key(user_id), user_id) for user_id in selected]
    if any(type(rank) is not int for rank, _ in ranked):
        raise TypeError("Explicit order keys must be integers, not bool")
    if len({rank for rank, _ in ranked}) != len(ranked):
        raise SplitError("Explicit order keys must establish a strict total order")
    return [user_id for _, user_id in sorted(ranked, key=lambda pair: pair[0])]


def split_equal[UserId: Hashable](
    amount: int,
    participants: Sequence[UserId],
    *,
    group_members: Collection[UserId],
    order_key: Callable[[UserId], int],
) -> dict[UserId, int]:
    """Разделить расход; первые по переданному ID-порядку получают остаток.

    order_key должен быть чистым и соответствовать будущему согласованному порядку
    user_id. До закрытия Q-02 этот параметр обязателен. Payer здесь не требуется:
    проверка его actor/членства принадлежит будущему финансовому сервису.
    """
    validate_expense_amount(amount)
    ordered = _ordered(participants, _group(group_members), order_key)
    quotient, remainder = divmod(amount, len(ordered))
    return {
        user_id: quotient + (1 if index < remainder else 0)
        for index, user_id in enumerate(ordered)
    }


def split_custom[UserId: Hashable](
    amount: int,
    shares: Sequence[tuple[UserId, int]],
    *,
    group_members: Collection[UserId],
    order_key: Callable[[UserId], int],
) -> dict[UserId, int]:
    """Проверить явные пары ID/копейки; не терять дубли через входной dict."""
    validate_expense_amount(amount)
    entries = tuple(shares)
    ordered = _ordered(
        [user_id for user_id, _ in entries], _group(group_members), order_key
    )
    for _, share in entries:
        validate_amount(share)
    if sum(share for _, share in entries) != amount:
        raise SplitError("Custom shares must exactly equal the expense amount")
    amounts = dict(entries)
    return {user_id: amounts[user_id] for user_id in ordered}


def split_by_items[UserId: Hashable](
    items: Sequence[ExpenseItem[UserId]],
    *,
    group_members: Collection[UserId],
    order_key: Callable[[UserId], int],
) -> tuple[int, dict[UserId, int]]:
    """Вернуть вычисленный итог и один снимок долей; каждую позицию делить отдельно."""
    rows = tuple(items)
    if not 1 <= len(rows) <= MAX_ITEMS:
        raise SplitError("A receipt must contain between 1 and 50 items")
    members = _group(group_members)
    total = 0
    shares: dict[UserId, int] = {}
    for item in rows:
        if not isinstance(item.title, str):
            raise TypeError("Item title must be a string")
        if not 1 <= len(item.title) <= MAX_TITLE_LENGTH:
            raise SplitError("Item title must contain between 1 and 120 code points")
        if not item.title.strip():
            raise ContractPendingError("Q-03: whitespace-only titles need agreement")
        # Q-03: no trim or Unicode normalization; code-point boundary awaits review.
        item_shares = split_equal(
            item.amount, item.participants, group_members=members, order_key=order_key
        )
        total += item.amount
        validate_expense_amount(total)
        for user_id, share in item_shares.items():
            shares[user_id] = shares.get(user_id, 0) + share
    ordered = _ordered(list(shares), members, order_key)
    return total, {user_id: shares[user_id] for user_id in ordered}
