"""Pure split functions: положительный int ID в BIGINT, числовой порядок (Q-02)."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from app.services.money import validate_amount, validate_expense_amount

MAX_GROUP_MEMBERS = 30
MAX_ITEMS = 50
MAX_TITLE_LENGTH = 120
MAX_USER_ID = 9_223_372_036_854_775_807


class SplitError(ValueError):
    """Некорректный диапазон ID, состав, доли или позиции."""


class ContractPendingError(RuntimeError):
    """Открытый Q-03 о названиях; не переводить автоматически в HTTP 400."""


@dataclass(frozen=True, slots=True)
class ExpenseItem:
    """Вход одной позиции в копейках; это не ORM/Pydantic/API-схема."""

    title: str
    amount: int
    participants: Sequence[int]


def _validated_ids(user_ids: Collection[int]) -> tuple[int, ...]:
    """Проверить каждый ID до set/dict, исключая bool и числовые подмены."""
    ids = tuple(user_ids)
    for user_id in ids:
        if type(user_id) is not int:
            raise TypeError("User ID must be an integer, not bool or a coerced value")
        if not 1 <= user_id <= MAX_USER_ID:
            raise SplitError("User ID must be a positive signed BIGINT")
    return ids


def _group(group_members: Collection[int]) -> set[int]:
    members = _validated_ids(group_members)
    if not 1 <= len(members) <= MAX_GROUP_MEMBERS:
        raise SplitError("Group must contain between 1 and 30 members")
    unique = set(members)
    if len(unique) != len(members):
        raise SplitError("Group context contains duplicate members")
    return unique


def _ordered(participants: Sequence[int], members: set[int]) -> list[int]:
    selected = _validated_ids(participants)
    if not 1 <= len(selected) <= MAX_GROUP_MEMBERS:
        raise SplitError("Select between 1 and 30 participants")
    if len(set(selected)) != len(selected):
        raise SplitError("Participants must be unique")
    if not set(selected) <= members:
        raise SplitError("Every participant must belong to the group")
    return sorted(selected)


def split_equal(
    amount: int,
    participants: Sequence[int],
    *,
    group_members: Collection[int],
) -> dict[int, int]:
    """Разделить расход; первые по возрастанию числового ID получают остаток.

    Payer здесь не требуется:
    проверка его actor/членства принадлежит будущему финансовому сервису.
    """
    validate_expense_amount(amount)
    ordered = _ordered(participants, _group(group_members))
    quotient, remainder = divmod(amount, len(ordered))
    return {
        user_id: quotient + (1 if index < remainder else 0)
        for index, user_id in enumerate(ordered)
    }


def split_custom(
    amount: int,
    shares: Sequence[tuple[int, int]],
    *,
    group_members: Collection[int],
) -> dict[int, int]:
    """Проверить явные пары ID/копейки; не терять дубли через входной dict."""
    validate_expense_amount(amount)
    entries = tuple(shares)
    ordered = _ordered([user_id for user_id, _ in entries], _group(group_members))
    for _, share in entries:
        validate_amount(share)
    if sum(share for _, share in entries) != amount:
        raise SplitError("Custom shares must exactly equal the expense amount")
    amounts = dict(entries)
    return {user_id: amounts[user_id] for user_id in ordered}


def split_by_items(
    items: Sequence[ExpenseItem],
    *,
    group_members: Collection[int],
) -> tuple[int, dict[int, int]]:
    """Вернуть вычисленный итог и один снимок долей; каждую позицию делить отдельно."""
    rows = tuple(items)
    if not 1 <= len(rows) <= MAX_ITEMS:
        raise SplitError("A receipt must contain between 1 and 50 items")
    members = _group(group_members)
    total = 0
    shares: dict[int, int] = {}
    for item in rows:
        if not isinstance(item.title, str):
            raise TypeError("Item title must be a string")
        if not 1 <= len(item.title) <= MAX_TITLE_LENGTH:
            raise SplitError("Item title must contain between 1 and 120 code points")
        if not item.title.strip():
            raise ContractPendingError("Q-03: whitespace-only titles need agreement")
        # Q-03: no trim or Unicode normalization; code-point boundary awaits review.
        item_shares = split_equal(item.amount, item.participants, group_members=members)
        total += item.amount
        validate_expense_amount(total)
        for user_id, share in item_shares.items():
            shares[user_id] = shares.get(user_id, 0) + share
    ordered = _ordered(list(shares), members)
    return total, {user_id: shares[user_id] for user_id in ordered}
