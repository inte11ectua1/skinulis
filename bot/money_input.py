"""Human RUB input -> canonical wire string; no splitting, rounding or floats."""

import re

# Only ordinary/non-breaking spaces at the edges. Tabs, newlines, embedded spaces,
# signs, grouping, Unicode digits and leading zeroes are deliberately rejected.
_PATTERN = re.compile(r"(0|[1-9][0-9]*)(?:[.,]([0-9]{1,2}))?")


def parse_money(value: str, *, zero: bool = False) -> str:
    match = _PATTERN.fullmatch(value.strip(" \u00a0\u202f"))
    if match is None:
        raise ValueError("Enter rubles with at most two decimal digits")
    whole, fraction = match.groups()
    canonical = whole + "." + (fraction or "").ljust(2, "0")
    if not zero and canonical == "0.00":
        raise ValueError("Use a positive amount")
    return canonical
