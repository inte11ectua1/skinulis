"""Internal O-05 receipt calculations; proposed wire DTOs are not asserted here."""

from copy import deepcopy
from itertools import permutations
from random import Random
from typing import Any

import pytest

from app.services.expenses import ByItemsExpense, ReceiptItemInput, prepare_expense
from app.services.money import MoneyError
from app.services.splits import ExpenseItem, SplitError, split_by_items

MEMBERS = (10, 20, 30)


def restaurant() -> ByItemsExpense:
    return ByItemsExpense(
        " Ресторан ",
        (
            ReceiptItemInput("Паста", "700.00", (10,)),
            ReceiptItemInput("Стейк", "1100.00", (20,)),
            ReceiptItemInput("Салат", "500.00", (30,)),
            ReceiptItemInput("Пицца", "900.00", (30, 10, 20)),
        ),
    )


def test_restaurant_prepares_each_item_and_one_final_snapshot() -> None:
    draft = restaurant()
    value = prepare_expense(draft, MEMBERS)
    assert value.title == "Ресторан" and value.split_mode == "by_items"
    assert value.amount_kopecks == 320000
    assert value.shares == ((10, 100000), (20, 140000), (30, 80000))
    assert [item.position for item in value.items] == [1, 2, 3, 4]
    assert value.items[-1].shares == ((10, 30000), (20, 30000), (30, 30000))
    assert draft.title == " Ресторан "


def test_two_kopecks_are_split_per_item_and_selected_zeros_survive() -> None:
    value = prepare_expense(
        ByItemsExpense(
            "Чек",
            (
                ReceiptItemInput("Чай", "0.01", MEMBERS),
                ReceiptItemInput("Сбор", "0.01", MEMBERS),
            ),
        ),
        MEMBERS,
    )
    assert value.amount_kopecks == 2
    assert value.shares == ((10, 2), (20, 0), (30, 0))
    assert all(item.shares == ((10, 1), (20, 0), (30, 0)) for item in value.items)


def test_overlapping_consumer_sets_form_union_including_zero() -> None:
    value = prepare_expense(
        ByItemsExpense(
            "Чек",
            (
                ReceiptItemInput("Первое", "0.01", (10, 20)),
                ReceiptItemInput("Второе", "0.01", (20, 30)),
            ),
        ),
        MEMBERS,
    )
    assert value.shares == ((10, 1), (20, 1), (30, 0))
    assert value.items[1].shares == ((20, 1), (30, 0))


def test_participant_permutations_are_deterministic_without_mutating_inputs() -> None:
    for order in permutations(MEMBERS):
        mutable: Any = list(order)
        rows: Any = [ReceiptItemInput(" e\u0301 ", "100.00", mutable)]
        before = deepcopy(rows)
        prepared = prepare_expense(ByItemsExpense(" Чек ", rows), MEMBERS)
        assert rows == before and mutable == list(order)
        assert prepared.items[0].title == "é"
        assert prepared.shares == ((10, 3334), (20, 3333), (30, 3333))


@pytest.mark.parametrize("count", [1, 50])
def test_item_count_boundaries(count: int) -> None:
    value = prepare_expense(
        ByItemsExpense(
            "Чек", tuple(ReceiptItemInput("Чай", "0.01", (20,)) for _ in range(count))
        ),
        MEMBERS,
    )
    assert len(value.items) == count and value.amount_kopecks == count
    assert value.shares == ((20, count),)


@pytest.mark.parametrize("count", [0, 51])
def test_invalid_item_count_is_not_truncated(count: int) -> None:
    with pytest.raises(SplitError):
        prepare_expense(
            ByItemsExpense(
                "Чек",
                tuple(ReceiptItemInput("Чай", "0.01", (20,)) for _ in range(count)),
            ),
            MEMBERS,
        )


@pytest.mark.parametrize(
    "consumers", [(), (10, 10), (40,), (True,), (10.0,), ("10",), (0,), (2**63,)]
)
def test_invalid_consumer_sets_and_strict_ids(consumers: Any) -> None:
    with pytest.raises((SplitError, TypeError)):
        prepare_expense(
            ByItemsExpense("Чек", (ReceiptItemInput("Чай", "1.00", consumers),)),
            MEMBERS,
        )


@pytest.mark.parametrize(
    "money",
    [
        "0.00",
        "-1.00",
        "-0.00",
        "01.00",
        "+1.00",
        " 1.00",
        "1.0",
        "1e2",
        "1,00",
        "١.٠٠",
        "1000000.01",
    ],
)
def test_invalid_item_money(money: str) -> None:
    with pytest.raises(MoneyError):
        prepare_expense(
            ByItemsExpense("Чек", (ReceiptItemInput("Чай", money, MEMBERS),)), MEMBERS
        )


@pytest.mark.parametrize("money", [1, True, 1.0, None])
def test_money_does_not_coerce_non_strings(money: Any) -> None:
    with pytest.raises(TypeError):
        prepare_expense(
            ByItemsExpense("Чек", (ReceiptItemInput("Чай", money, MEMBERS),)), MEMBERS
        )


@pytest.mark.parametrize(
    "title", ["", " \u2003 ", "a" * 121, "👩\u200d💻", "Е\x00да", "Е\u200bда"]
)
def test_item_title_uses_approved_financial_normalization(title: str) -> None:
    with pytest.raises(ValueError):
        prepare_expense(
            ByItemsExpense("Чек", (ReceiptItemInput(title, "1.00", MEMBERS),)), MEMBERS
        )


def test_total_limit_is_checked_after_aggregation() -> None:
    with pytest.raises(MoneyError):
        prepare_expense(
            ByItemsExpense(
                "Чек",
                (
                    ReceiptItemInput("Первое", "600000.00", (20,)),
                    ReceiptItemInput("Второе", "600000.00", (20,)),
                ),
            ),
            MEMBERS,
        )
    maximum = prepare_expense(
        ByItemsExpense(
            "Чек",
            (
                ReceiptItemInput("Первое", "500000.00", (20,)),
                ReceiptItemInput("Второе", "500000.00", (20,)),
            ),
        ),
        MEMBERS,
    )
    assert maximum.amount_kopecks == 100000000


def test_preparation_agrees_with_existing_o02_for_generated_receipts() -> None:
    random = Random(23)
    for _ in range(20):
        inputs: list[ReceiptItemInput] = []
        pure: list[ExpenseItem] = []
        for number in range(random.randint(1, 12)):
            amount = random.randint(1, 20000)
            consumers = tuple(random.sample(MEMBERS, random.randint(1, 3)))
            inputs.append(
                ReceiptItemInput(
                    str(number), f"{amount // 100}.{amount % 100:02d}", consumers
                )
            )
            pure.append(ExpenseItem(str(number), amount, consumers))
        prepared = prepare_expense(ByItemsExpense("Чек", tuple(inputs)), MEMBERS)
        total, shares = split_by_items(pure, group_members=MEMBERS)
        assert (prepared.amount_kopecks, dict(prepared.shares)) == (total, shares)
        assert all(
            sum(value for _, value in item.shares) == item.amount_kopecks
            for item in prepared.items
        )
