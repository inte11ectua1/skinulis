"""O-08 seeded metamorphic tests across full preparation, not a second split oracle."""

from copy import deepcopy
from random import Random

import pytest

from app.services.expenses import (
    ByItemsExpense,
    CustomExpense,
    EqualExpense,
    ReceiptItemInput,
    prepare_expense,
)
from app.services.money import MAX_EXPENSE_KOPECKS, format_money
from app.services.settlement_plan import greedy_plan


@pytest.mark.parametrize("seed", [6108, 7108, 8108])
def test_generated_receipt_preparation_conserves_and_keeps_selected_zeros(
    seed: int,
) -> None:
    rng = Random(seed)
    for case in range(60):
        members = rng.sample(range(1, 2**20), rng.randrange(1, 31))
        items = tuple(
            ReceiptItemInput(
                f"Item {i}",
                format_money(rng.randrange(1, 10001)),
                tuple(rng.sample(members, rng.randrange(1, len(members) + 1))),
            )
            for i in range(rng.randrange(1, 15))
        )
        draft = ByItemsExpense("Generated", items)
        saved = deepcopy(draft)
        result = prepare_expense(draft, members)
        selected = {u for item in items for u in item.participants}
        assert {u for u, _ in result.shares} == selected
        assert sum(a for _, a in result.shares) == result.amount_kopecks
        assert all(type(a) is int and a >= 0 for _, a in result.shares)
        assert [u for u, _ in result.shares] == sorted(selected)
        # Independent conservation and per-item difference/rank properties.
        for item in result.items:
            amounts = dict(item.shares)
            assert sum(amounts.values()) == item.amount_kopecks
            assert max(amounts.values()) - min(amounts.values()) <= 1
            assert list(amounts.values()) == sorted(amounts.values(), reverse=True)
        permuted = ByItemsExpense(
            "Generated",
            tuple(
                ReceiptItemInput(i.title, i.amount, tuple(reversed(i.participants)))
                for i in reversed(items)
            ),
        )
        other = prepare_expense(permuted, list(reversed(members)))
        assert (other.amount_kopecks, other.shares) == (
            result.amount_kopecks,
            result.shares,
        )
        assert prepare_expense(draft, members) == result and draft == saved
        custom = CustomExpense(
            "Custom",
            format_money(result.amount_kopecks),
            tuple((u, format_money(a)) for u, a in reversed(result.shares)),
        )
        assert prepare_expense(custom, members).shares == result.shares
        equal = prepare_expense(
            EqualExpense(
                "Equal",
                format_money([1, 10000, MAX_EXPENSE_KOPECKS][case % 3]),
                tuple(members),
            ),
            members,
        )
        values = [v for _, v in equal.shares]
        assert sum(values) == equal.amount_kopecks
        assert max(values) - min(values) <= 1
        assert values == sorted(values, reverse=True)


@pytest.mark.parametrize("seed", [6108, 7108, 8108])
def test_generated_plans_discharge_every_prefix_without_overpay(seed: int) -> None:
    rng = Random(seed)
    for _ in range(100):
        ids = rng.sample(range(1, 2**30), rng.randrange(2, 31))
        vector = {
            uid: rng.choice([0, -1, 1]) * rng.randrange(1, 10**30) for uid in ids[:-1]
        }
        vector[ids[-1]] = -sum(vector.values())
        original = vector.copy()
        plan = greedy_plan(vector)
        assert plan == greedy_plan(dict(reversed(list(vector.items()))))
        remaining = vector.copy()
        for transfer in plan:
            sender, receiver, amount = (
                transfer.sender_id,
                transfer.receiver_id,
                transfer.amount_kopecks,
            )
            assert type(amount) is int and 0 < amount <= -remaining[sender]
            assert amount <= remaining[receiver]
            remaining[sender] += amount
            remaining[receiver] -= amount
            assert sum(remaining.values()) == 0
        assert set(remaining.values()) == {0} and vector == original
        nonzero = sum(v != 0 for v in vector.values())
        assert len(plan) <= max(0, nonzero - 1)
