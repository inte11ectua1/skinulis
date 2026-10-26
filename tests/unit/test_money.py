"""O-01 M-* на уровне pure functions; Q-01 cases проверяют Draft-предохранитель."""

from decimal import Decimal
from typing import cast

import pytest

from app.services.money import (
    MAX_EXPENSE_KOPECKS,
    ContractPendingError,
    MoneyError,
    format_money,
    parse_money,
    validate_amount,
    validate_expense_amount,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.00", 0),
        ("0.01", 1),
        ("0.10", 10),
        ("1.00", 100),
        ("100.00", 10_000),
        ("1000000.00", MAX_EXPENSE_KOPECKS),
        ("1500000.01", 150_000_001),
    ],
)
def test_exact_parser_and_formatter(value: str, expected: int) -> None:
    """M-001/M-002/M-010/M-017: parser сам по себе не ограничен одним расходом."""
    assert parse_money(value) == expected
    assert format_money(expected) == value


def test_decimal_addition_uses_only_kopecks() -> None:
    """M-006."""
    assert parse_money("0.10") + parse_money("0.20") == 30
    assert format_money(parse_money("0.10") + parse_money("0.20")) == "0.30"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1",
        "1.0",
        "1.000",
        ".01",
        "0.009",
        "1e2",
        "1e2.00",
        "1,00",
        "1 000.00",
        "NaN",
        "Infinity",
        "1.00.00",
        "$1.00",
        "-0.01",
        "-1.00",
    ],
)
def test_known_invalid_money_is_not_coerced_or_rounded(value: str) -> None:
    """M-005/M-008/M-009/M-013: уже определённые ошибки."""
    with pytest.raises(MoneyError):
        parse_money(value)


@pytest.mark.parametrize(
    "value", [None, True, False, 1, 1.25, [], {}, b"1.00", Decimal("1.00")]
)
def test_parser_rejects_non_string_types(value: object) -> None:
    """M-007: cast только для намеренной проверки runtime-границы."""
    with pytest.raises(TypeError):
        parse_money(cast(str, value))


@pytest.mark.parametrize("amount", [None, True, False, "1", 1.25, Decimal("1")])
def test_money_helpers_reject_non_integer_kopecks(amount: object) -> None:
    with pytest.raises(TypeError):
        validate_amount(cast(int, amount))
    with pytest.raises(TypeError):
        format_money(cast(int, amount))


@pytest.mark.parametrize("amount", [1, MAX_EXPENSE_KOPECKS])
def test_expense_inclusive_limits(amount: int) -> None:
    assert validate_expense_amount(amount) == amount


@pytest.mark.parametrize("amount", [-1, 0, MAX_EXPENSE_KOPECKS + 1])
def test_expense_amount_outside_limits(amount: int) -> None:
    """M-003/M-004/M-005."""
    with pytest.raises(MoneyError):
        validate_expense_amount(amount)


def test_parser_context_does_not_leak_the_expense_limit() -> None:
    """M-003/M-004/M-010/M-011/M-017: сумма, доля и цена проверяются по контексту."""
    assert parse_money("0.00") == 0
    assert parse_money("0.01", minimum=1, maximum=MAX_EXPENSE_KOPECKS) == 1
    assert (
        parse_money("1000000.00", minimum=1, maximum=MAX_EXPENSE_KOPECKS)
        == MAX_EXPENSE_KOPECKS
    )
    with pytest.raises(MoneyError):
        parse_money("0.00", minimum=1)
    with pytest.raises(MoneyError):
        parse_money("1000000.01", maximum=MAX_EXPENSE_KOPECKS)
    assert parse_money("1500000.01", minimum=1) == 150_000_001
    assert validate_amount(150_000_001, minimum=1) == 150_000_001


@pytest.mark.parametrize(("minimum", "maximum"), [(-1, None), (2, 1)])
def test_inconsistent_context_bounds_are_programmer_errors(
    minimum: int, maximum: int | None
) -> None:
    with pytest.raises(ValueError, match="bounds"):
        validate_amount(1, minimum=minimum, maximum=maximum)


@pytest.mark.parametrize(
    ("minimum", "maximum"), [(True, None), (0, True), ("0", None), (0, "2")]
)
def test_bounds_are_also_strict_integers(minimum: object, maximum: object) -> None:
    with pytest.raises(TypeError):
        validate_amount(
            1, minimum=cast(int, minimum), maximum=cast(int | None, maximum)
        )


def test_non_negative_context_rejects_negative_kopecks() -> None:
    with pytest.raises(MoneyError):
        validate_amount(-1)


@pytest.mark.parametrize(
    "amount", [0, 1, 99, 100, 101, 10_000, 100_000_000, 150_000_001, 10**40 + 1]
)
def test_integer_round_trip(amount: int) -> None:
    rendered = format_money(amount)
    whole, fractional = rendered.split(".")
    assert whole.isascii() and whole.isdigit()
    assert len(fractional) == 2
    assert parse_money(rendered) == amount


@pytest.mark.parametrize(
    "value", [" 1.00", "1.00 ", "01.00", "+1.00", "١.٠٠", "-0.00", "\t1.00\n"]
)
def test_unresolved_q01_spelling_does_not_become_a_validation_decision(
    value: str,
) -> None:
    """M-014/M-015: ни принятие, ни окончательный отказ; явный блокер Draft."""
    with pytest.raises(ContractPendingError, match="Q-01"):
        parse_money(value)


@pytest.mark.parametrize("amount", [-1, -100])
def test_signed_formatter_waits_for_q01(amount: int) -> None:
    """M-016: API-представление отрицательных балансов ещё не принято."""
    with pytest.raises(ContractPendingError, match="Q-01"):
        format_money(amount)
