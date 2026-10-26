"""O-02: арифметика без БД/HTTP. ID-порядок задан явно, пока Q-02 открыт."""

from copy import deepcopy
from itertools import permutations
from random import Random
from typing import cast

import pytest

from app.services.money import MAX_EXPENSE_KOPECKS, ContractPendingError, MoneyError
from app.services.splits import (
    ExpenseItem,
    SplitError,
    split_by_items,
    split_custom,
    split_equal,
)

GROUP = (10, 20, 30)


def numeric_fixture_order(user_id: int) -> int:
    """Числовой порядок синтетической фикстуры, не принятый тип моделей users."""
    return user_id


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (10_000, {10: 3334, 20: 3333, 30: 3333}),
        (1, {10: 1, 20: 0, 30: 0}),
        (MAX_EXPENSE_KOPECKS, {10: 33333334, 20: 33333333, 30: 33333333}),
    ],
)
def test_equal_exact_examples(amount: int, expected: dict[int, int]) -> None:
    """E-001/E-002/E-010."""
    assert (
        split_equal(
            amount, [30, 10, 20], group_members=GROUP, order_key=numeric_fixture_order
        )
        == expected
    )


@pytest.mark.parametrize("participants", list(permutations(GROUP)))
def test_equal_all_input_permutations(participants: tuple[int, ...]) -> None:
    """E-006: проверяем и отображение, и порядок нового результата."""
    result = split_equal(
        10_000, participants, group_members=GROUP, order_key=numeric_fixture_order
    )
    assert result == {10: 3334, 20: 3333, 30: 3333}
    assert list(result) == [10, 20, 30]


def test_single_consumer_can_exclude_the_payer() -> None:
    """E-003/K-009: payer10 не обязателен среди потребителей."""
    assert split_equal(
        10_000, [20], group_members=GROUP, order_key=numeric_fixture_order
    ) == {20: 10_000}
    assert split_custom(
        1, [(20, 1)], group_members=GROUP, order_key=numeric_fixture_order
    ) == {20: 1}


@pytest.mark.parametrize(
    "participants", [[], [10, 10, 20], [10, 40], list(range(1, 32))]
)
def test_invalid_equal_selection(participants: list[int]) -> None:
    """E-004/E-005/E-009 и предел 30."""
    with pytest.raises(SplitError):
        split_equal(
            100, participants, group_members=GROUP, order_key=numeric_fixture_order
        )


@pytest.mark.parametrize("members", [[], [10, 10], list(range(1, 32))])
def test_invalid_group_context_is_not_normalized(members: list[int]) -> None:
    with pytest.raises(SplitError):
        split_equal(1, [10], group_members=members, order_key=numeric_fixture_order)


@pytest.mark.parametrize("amount", [-1, 0, MAX_EXPENSE_KOPECKS + 1])
def test_all_split_modes_enforce_expense_bounds(amount: int) -> None:
    with pytest.raises(MoneyError):
        split_equal(amount, [10], group_members=GROUP, order_key=numeric_fixture_order)
    with pytest.raises(MoneyError):
        split_custom(
            amount, [(10, amount)], group_members=GROUP, order_key=numeric_fixture_order
        )
    with pytest.raises(MoneyError):
        split_by_items(
            [ExpenseItem("Item", amount, [10])],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


@pytest.mark.parametrize("amount", [True, False, "1", None, 1.25])
def test_all_split_modes_reject_coerced_money(amount: object) -> None:
    value = cast(int, amount)
    with pytest.raises(TypeError):
        split_equal(value, [10], group_members=GROUP, order_key=numeric_fixture_order)
    with pytest.raises(TypeError):
        split_custom(
            1, [(10, value)], group_members=GROUP, order_key=numeric_fixture_order
        )
    with pytest.raises(TypeError):
        split_by_items(
            [ExpenseItem("Item", value, [10])],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


def test_custom_preserves_explicit_zero_and_exact_values() -> None:
    """K-001/M-010."""
    assert split_custom(
        10_000,
        [(30, 6000), (10, 0), (20, 4000)],
        group_members=GROUP,
        order_key=numeric_fixture_order,
    ) == {10: 0, 20: 4000, 30: 6000}


@pytest.mark.parametrize(
    "shares",
    [
        [(10, 4000), (20, 5999)],
        [(10, 4000), (20, 6001)],
        [(10, 4000), (10, 6000)],
        [],
        [(40, 10_000)],
    ],
)
def test_invalid_custom_shares(shares: list[tuple[int, int]]) -> None:
    """K-002/K-003/K-005/K-006 и чужой участник."""
    with pytest.raises(SplitError):
        split_custom(
            10_000, shares, group_members=GROUP, order_key=numeric_fixture_order
        )


def test_negative_custom_share_is_invalid_even_when_total_matches() -> None:
    """K-004."""
    with pytest.raises(MoneyError):
        split_custom(
            10_000,
            [(10, -1), (20, 10_001)],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


def test_restaurant_exact_total_and_snapshot() -> None:
    """I-001: позиции возвращаются как один итоговый снимок, без удвоения."""
    items = [
        ExpenseItem("Паста", 70_000, [10]),
        ExpenseItem("Стейк", 110_000, [20]),
        ExpenseItem("Салат", 50_000, [30]),
        ExpenseItem("Пицца", 90_000, [30, 10, 20]),
    ]
    total, shares = split_by_items(
        items, group_members=GROUP, order_key=numeric_fixture_order
    )
    assert total == 320_000
    assert shares == {10: 100_000, 20: 140_000, 30: 80_000}
    assert sum(shares.values()) == total


def test_item_remainders_are_not_reallocated_from_the_receipt_total() -> None:
    """I-002: два раза по копейке != один equal на общую сумму."""
    items = [ExpenseItem("First", 1, GROUP), ExpenseItem("Second", 1, GROUP)]
    assert split_by_items(
        items, group_members=GROUP, order_key=numeric_fixture_order
    ) == (2, {10: 2, 20: 0, 30: 0})
    assert split_equal(
        2, GROUP, group_members=GROUP, order_key=numeric_fixture_order
    ) == {10: 1, 20: 1, 30: 0}


def test_different_consumers_per_item_and_item_permutations() -> None:
    """I-003/I-014."""
    for items in permutations(
        [ExpenseItem("First", 1, [20, 10]), ExpenseItem("Second", 1, [30, 20])]
    ):
        assert split_by_items(
            items, group_members=GROUP, order_key=numeric_fixture_order
        ) == (2, {10: 1, 20: 1, 30: 0})


@pytest.mark.parametrize("participants", [[], [10, 10], [20, 40]])
def test_invalid_item_participants(participants: list[int]) -> None:
    """I-004/I-005/I-016."""
    with pytest.raises(SplitError):
        split_by_items(
            [ExpenseItem("Item", 10, participants)],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


@pytest.mark.parametrize("count", [0, 51])
def test_receipt_item_count_rejects_outside_limits(count: int) -> None:
    """I-006/I-008."""
    with pytest.raises(SplitError):
        split_by_items(
            [ExpenseItem("Item", 1, [20])] * count,
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


def test_fifty_items_and_thirty_group_members_are_allowed() -> None:
    """I-007/E-007, все нулевые выбранные доли сохраняются в результате."""
    members = tuple(range(1, 31))
    total, shares = split_by_items(
        [ExpenseItem("Item", 1, members)] * 50,
        group_members=members,
        order_key=numeric_fixture_order,
    )
    assert total == 50
    assert shares == {user_id: 50 if user_id == 1 else 0 for user_id in members}


def test_receipt_limit_applies_to_sum_not_only_each_item() -> None:
    """I-009/I-010."""
    accepted = [ExpenseItem("Item", 50_000_000, [20])] * 2
    assert split_by_items(
        accepted, group_members=GROUP, order_key=numeric_fixture_order
    ) == (MAX_EXPENSE_KOPECKS, {20: MAX_EXPENSE_KOPECKS})
    with pytest.raises(MoneyError):
        split_by_items(
            [ExpenseItem("Item", 60_000_000, [20])] * 2,
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


@pytest.mark.parametrize("title", ["a", "а" * 120])
def test_known_valid_title_boundaries(title: str) -> None:
    assert split_by_items(
        [ExpenseItem(title, 1, [20])],
        group_members=GROUP,
        order_key=numeric_fixture_order,
    ) == (1, {20: 1})


@pytest.mark.parametrize("title", ["", "а" * 121])
def test_known_invalid_title_boundaries(title: str) -> None:
    with pytest.raises(SplitError):
        split_by_items(
            [ExpenseItem(title, 1, [20])],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


def test_title_type_is_not_coerced() -> None:
    with pytest.raises(TypeError):
        split_by_items(
            [ExpenseItem(cast(str, 1), 1, [20])],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


def test_whitespace_title_is_deferred_not_silently_accepted_or_trimmed() -> None:
    with pytest.raises(ContractPendingError, match="Q-03"):
        split_by_items(
            [ExpenseItem(" ", 1, [20])],
            group_members=GROUP,
            order_key=numeric_fixture_order,
        )


def test_tips_are_regular_positive_items() -> None:
    """I-015: отрицательная скидка покрыта тестами отрицательных item amounts."""
    assert split_by_items(
        [ExpenseItem("Tips", 1, [20])],
        group_members=GROUP,
        order_key=numeric_fixture_order,
    ) == (1, {20: 1})


def test_explicit_order_is_independent_of_the_user_id_model() -> None:
    """E-008 остаётся Q-02: opaque labels и явно переданный порядок, не API IDs."""
    ranks = {"two": 2, "ten": 10}
    assert split_equal(
        1, ["ten", "two"], group_members=ranks, order_key=ranks.__getitem__
    ) == {"two": 1, "ten": 0}
    assert split_equal(
        1, [10, 2], group_members=[2, 10], order_key=numeric_fixture_order
    ) == {2: 1, 10: 0}


def test_ambiguous_order_is_not_resolved_by_input_order() -> None:
    with pytest.raises(SplitError, match="strict total order"):
        split_equal(1, GROUP, group_members=GROUP, order_key=lambda _: 0)


@pytest.mark.parametrize("rank", [True, "1"])
def test_order_keys_are_strict_integer_ranks(rank: object) -> None:
    with pytest.raises(TypeError):
        split_equal(1, [10], group_members=GROUP, order_key=lambda _: cast(int, rank))


def test_bool_does_not_alias_an_integer_member() -> None:
    with pytest.raises(TypeError):
        split_equal(1, [True], group_members=[1], order_key=numeric_fixture_order)
    with pytest.raises(TypeError):
        split_equal(1, [1], group_members=[True], order_key=numeric_fixture_order)


def test_inputs_are_unchanged_and_results_do_not_alias_them() -> None:
    members = [10, 20, 30]
    participants = [30, 10, 20]
    custom = [(30, 6000), (10, 0), (20, 4000)]
    items = [ExpenseItem("Item", 10_000, participants)]
    before = deepcopy((members, participants, custom, items))
    equal = split_equal(
        10_000, participants, group_members=members, order_key=numeric_fixture_order
    )
    explicit = split_custom(
        10_000, custom, group_members=members, order_key=numeric_fixture_order
    )
    _, receipt = split_by_items(
        items, group_members=members, order_key=numeric_fixture_order
    )
    assert (members, participants, custom, items) == before
    equal[10] = explicit[10] = receipt[10] = -1
    assert (members, participants, custom, items) == before
    assert (
        split_equal(
            10_000, participants, group_members=members, order_key=numeric_fixture_order
        )[10]
        == 3334
    )


def test_invalid_later_item_does_not_mutate_earlier_inputs() -> None:
    items = [ExpenseItem("First", 100, [10, 20]), ExpenseItem("Second", 1, [40])]
    before = deepcopy(items)
    with pytest.raises(SplitError):
        split_by_items(items, group_members=GROUP, order_key=numeric_fixture_order)
    assert items == before


@pytest.mark.parametrize("member_count", range(1, 31))
def test_equal_conservation_fairness_and_repeatability(member_count: int) -> None:
    members = tuple(range(1, member_count + 1))
    for amount in {
        1,
        member_count,
        member_count + 1,
        9999,
        10_000,
        MAX_EXPENSE_KOPECKS,
    }:
        result = split_equal(
            amount,
            members[::-1],
            group_members=members,
            order_key=numeric_fixture_order,
        )
        assert sum(result.values()) == amount
        assert set(result) == set(members)
        assert min(result.values()) >= 0
        assert max(result.values()) - min(result.values()) <= 1
        assert list(result.values()) == sorted(result.values(), reverse=True)
        assert result == split_equal(
            amount, members, group_members=members, order_key=numeric_fixture_order
        )
        assert (
            split_custom(
                amount,
                list(result.items()),
                group_members=members,
                order_key=numeric_fixture_order,
            )
            == result
        )


@pytest.mark.parametrize("seed", range(10))
def test_receipt_conservation_under_deterministic_generated_inputs(seed: int) -> None:
    random = Random(seed)
    members = tuple(range(1, 31))
    items = [
        ExpenseItem(
            f"Item {index}",
            random.randint(1, 10_000),
            random.sample(members, random.randint(1, 30)),
        )
        for index in range(1, 51)
    ]
    before = deepcopy(items)
    total, result = split_by_items(
        items, group_members=members, order_key=numeric_fixture_order
    )
    assert total == sum(item.amount for item in items)
    assert sum(result.values()) == total
    assert all(amount >= 0 for amount in result.values())
    assert set(result) == {user_id for item in items for user_id in item.participants}
    permuted = [
        ExpenseItem(item.title, item.amount, list(reversed(item.participants)))
        for item in reversed(items)
    ]
    assert split_by_items(
        permuted, group_members=members, order_key=numeric_fixture_order
    ) == (total, result)
    assert items == before
