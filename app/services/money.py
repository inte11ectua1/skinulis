"""Целые копейки без I/O. Спорные варианты Q-01 намеренно не классифицируются.

До решения https://github.com/inte11ectua1/skinulis/issues/11#issuecomment-6425190867
принимать в parser только бесспорное подмножество строк. ContractPendingError —
ограничение Draft, а не ошибка пользовательского ввода будущего API.
"""

import re

MAX_EXPENSE_KOPECKS = 100_000_000

_CANONICAL_MONEY = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2}")
_UNDECIDED_MONEY = re.compile(r"[+-]?\d+\.\d{2}")


class MoneyError(ValueError):
    """Нарушение согласованного формата или контекстного диапазона суммы."""


class ContractPendingError(RuntimeError):
    """Нужен ответ команды; не переводить автоматически в HTTP 400."""


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
    """Разобрать бесспорную строку RUB; отдельно применить контекстные пределы.

    Не нормализует пробелы, знаки, Unicode-цифры и ведущие нули: это открытый Q-01.
    Отрицательная ненулевая каноническая сумма уже запрещена денежным доменом.
    """
    if not isinstance(value, str):
        raise TypeError("Money must be a string")
    if _CANONICAL_MONEY.fullmatch(value) is None:
        if (
            value.startswith("-")
            and _CANONICAL_MONEY.fullmatch(value[1:]) is not None
            and value[1:] != "0.00"
        ):
            raise MoneyError("Negative input amounts are not allowed")
        if _UNDECIDED_MONEY.fullmatch(value.strip()) is not None:
            raise ContractPendingError("Q-01: money spelling needs team agreement")
        raise MoneyError("Money must have a decimal point and exactly two digits")
    rubles, kopecks = value.split(".")
    # Accumulation also avoids CPython's configurable int(string) digit limit.
    amount = 0
    for digit in rubles:
        amount = amount * 10 + ord(digit) - ord("0")
    amount = amount * 100 + int(kopecks)
    return validate_amount(amount, minimum=minimum, maximum=maximum)


def format_money(amount: int) -> str:
    """Форматировать неотрицательные копейки; знак будущего баланса — открытый Q-01."""
    if type(amount) is not int:
        raise TypeError("Amount must be integer kopecks")
    if amount < 0:
        raise ContractPendingError("Q-01: signed balance output needs team agreement")
    rubles, kopecks = divmod(amount, 100)
    # Construct digits without a platform-dependent int-to-string length limit.
    digits: list[str] = []
    while rubles:
        rubles, digit = divmod(rubles, 10)
        digits.append(chr(ord("0") + digit))
    whole = "".join(reversed(digits)) if digits else "0"
    return f"{whole}.{kopecks:02d}"
