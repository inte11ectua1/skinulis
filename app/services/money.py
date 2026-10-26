"""Целые копейки без I/O; канонический формат по решению Q-01 в Issue #11."""

import re

MAX_EXPENSE_KOPECKS = 100_000_000

_CANONICAL_MONEY = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2}")


class MoneyError(ValueError):
    """Нарушение согласованного формата или контекстного диапазона суммы."""


def validate_amount(
    amount: int, *, minimum: int = 0, maximum: int | None = None
) -> int:
    """Проверить копейки в явно заданном контексте, без лимита расхода по умолчанию."""
    if type(amount) is not int:
        raise TypeError("Amount must be integer kopecks, not bool or a coerced value")
    if type(minimum) is not int or (maximum is not None and type(maximum) is not int):
        raise TypeError("Amount bounds must be integers")
    if minimum < 0 or (maximum is not None and maximum < minimum):
        raise ValueError("Invalid non-negative amount bounds")
    if amount < minimum or (maximum is not None and amount > maximum):
        raise MoneyError("Amount is outside the context bounds")
    return amount


def validate_expense_amount(amount: int) -> int:
    """Один расход: от 1 до 100000000 копеек включительно."""
    return validate_amount(amount, minimum=1, maximum=MAX_EXPENSE_KOPECKS)


def parse_money(value: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    """Каноническая ASCII-строка RUB → копейки, затем контекстные пределы.

    Без trim, нормализации, знаков, ведущих нулей и неявного приведения типов.
    """
    if not isinstance(value, str):
        raise TypeError("Money must be a string")
    if _CANONICAL_MONEY.fullmatch(value) is None:
        raise MoneyError("Money must be a canonical non-negative ASCII decimal string")
    rubles, kopecks = value.split(".")
    # Accumulation also avoids CPython's configurable int(string) digit limit.
    amount = 0
    for digit in rubles:
        amount = amount * 10 + ord(digit) - ord("0")
    amount = amount * 100 + int(kopecks)
    return validate_amount(amount, minimum=minimum, maximum=maximum)


def format_money(amount: int) -> str:
    """Форматировать целые копейки; минус только при отрицательном результате."""
    if type(amount) is not int:
        raise TypeError("Amount must be integer kopecks")
    sign = "-" if amount < 0 else ""
    rubles, kopecks = divmod(abs(amount), 100)
    # Construct digits without a platform-dependent int-to-string length limit.
    digits: list[str] = []
    while rubles:
        rubles, digit = divmod(rubles, 10)
        digits.append(chr(ord("0") + digit))
    whole = "".join(reversed(digits)) if digits else "0"
    return f"{sign}{whole}.{kopecks:02d}"
