"""Approved financial input rules; these are not HTTP DTO tests."""

from itertools import permutations
from secrets import token_urlsafe
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.services.expenses import (
    CustomExpense,
    EqualExpense,
    normalize_title,
    prepare_expense,
)
from app.services.money import MoneyError, format_money
from app.services.splits import SplitError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Еда", "Еда"),
        ("  Еда  ", "Еда"),
        ("\u2003Обед\u00a0", "Обед"),
        ("Еда  и ЧАЙ", "Еда  и ЧАЙ"),
        ("e\u0301", "é"),
        ("e\u0301" * 120, "é" * 120),
        ("🍵" * 120, "🍵" * 120),
        ("👋🏽", "👋🏽"),
        ("\nОбед\t", "Обед"),
    ],
)
def test_q03_normalizes_before_length_and_category_check(
    raw: str, expected: str
) -> None:
    assert normalize_title(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "\t\n\u2003\u00a0",
        "я" * 121,
        "e\u0301" * 121,
        "👩\u200d💻",
        "Е\u200bда",
        "Е\x00да",
        "Е\nда",
        "Е\tда",
        "Е\ufeffда",
        "Е\ud800да",
        "Е\ue000да",
        "Е\u0378да",
    ],
)
def test_q03_rejects_empty_long_or_category_c(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_title(raw)


@pytest.mark.parametrize("raw", [None, 1, True, [], b"food"])
def test_title_has_no_type_coercion(raw: Any) -> None:
    with pytest.raises(TypeError):
        normalize_title(raw)


def test_prepared_equal_is_sorted_exact_immutable_and_preserves_zero() -> None:
    for order in permutations((10, 2, 5)):
        expense = prepare_expense(EqualExpense(" Обед ", "100.00", order), [2, 5, 10])
        assert expense.title == "Обед"
        assert expense.split_mode == "equal"
        assert expense.shares == ((2, 3334), (5, 3333), (10, 3333))
        assert (
            sum(value for _, value in expense.shares) == expense.amount_kopecks == 10000
        )
    penny = prepare_expense(EqualExpense("Чай", "0.01", (10, 5, 2)), [2, 5, 10])
    assert penny.shares == ((2, 1), (5, 0), (10, 0))
    assert [format_money(value) for _, value in penny.shares] == [
        "0.01",
        "0.00",
        "0.00",
    ]


def test_custom_uses_rub_strings_and_keeps_selected_zero() -> None:
    draft = CustomExpense(
        " e\u0301 ", "100.00", ((10, "60.00"), (2, "0.00"), (5, "40.00"))
    )
    value = prepare_expense(draft, [2, 5, 10])
    assert value.title == "é" and value.split_mode == "custom"
    assert value.shares == ((2, 0), (5, 4000), (10, 6000))
    assert draft.title == " e\u0301 "


@pytest.mark.parametrize("amount", ["59.99", "60.01"])
def test_custom_does_not_correct_a_kopeck(amount: str) -> None:
    with pytest.raises(SplitError):
        prepare_expense(
            CustomExpense("Обед", "100.00", ((2, "40.00"), (5, amount))), [2, 5]
        )


@pytest.mark.parametrize(
    "money",
    [
        "0.00",
        "1000000.01",
        "-1.00",
        "-0.00",
        "01.00",
        "+1.00",
        "1.0",
        "1e2",
        "١.٠٠",
        " 1.00",
        "1.00 ",
    ],
)
def test_invalid_money_does_not_reach_prepared_snapshot(money: str) -> None:
    with pytest.raises(MoneyError):
        prepare_expense(EqualExpense("Еда", money, (2,)), [2])


@pytest.mark.parametrize("money", [1, 1.0, True, None])
def test_internal_money_input_is_not_coerced(money: Any) -> None:
    with pytest.raises(TypeError):
        prepare_expense(EqualExpense("Еда", money, (2,)), [2])


@pytest.mark.parametrize(
    "participants", [(), (2, 2), (2, 20), (True,), (1.0,), ("2",), (0,), (2**63,)]
)
def test_participant_validation_is_delegated_to_o02(participants: Any) -> None:
    with pytest.raises((SplitError, TypeError)):
        prepare_expense(EqualExpense("Еда", "1.00", participants), [2, 5])


def test_approved_expense_operations_are_published_in_both_actor_channels() -> None:
    paths = create_app(
        Settings(postgres_password=SecretStr(token_urlsafe(32)), _env_file=None)
    ).openapi()["paths"]
    for prefix in ("", "/internal"):
        assert {"post", "get"} <= paths[f"{prefix}/groups/{{group_id}}/expenses"].keys()
        assert "post" in paths[f"{prefix}/groups/{{group_id}}/expenses/preview"]
        assert {"get", "put", "delete"} <= paths[
            f"{prefix}/expenses/{{expense_id}}"
        ].keys()
