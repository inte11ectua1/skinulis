"""Telegram-native visual vocabulary. Names/amounts are presentation, never authority."""

import re
from collections import Counter
from html import escape

from bot.api_client import BotApi
from bot.dto import MemberProfile, Page

MODES = {"equal": "Поровну", "custom": "Указать суммы", "by_items": "По позициям"}
STATUSES = {
    "pending": "Ожидает",
    "confirmed": "Подтверждено",
    "rejected": "Отклонено",
    "cancelled": "Отменено",
}


def money(value: str) -> str:
    """Format a canonical server string without arithmetic or floats."""
    whole, dot, cents = value.partition(".")
    sign = "−" if whole.startswith("-") else ""
    digits = whole.lstrip("-")
    groups = [
        digits[max(0, len(digits) - i - 3) : len(digits) - i]
        for i in range(0, len(digits), 3)
    ]
    return (
        sign
        + " ".join(reversed(groups))
        + ("," + cents if dot and cents != "00" else "")
        + " ₽"
    )


def html_card(text: str) -> str:
    heading, _, body = text.partition("\n")
    if len(heading) > 100:
        heading, body = "Обратите внимание", text
    rows = []
    for row in body.split("\n"):
        safe = escape(row)
        rows.append(
            "<b>" + safe + "</b>" if re.fullmatch(r"[−0-9][0-9 ,]* ₽", row) else safe
        )
    return "<b>" + escape(heading) + "</b>" + ("\n" + "\n".join(rows) if body else "")


def member_names(members: list[MemberProfile]) -> dict[int, str]:
    bases = [(m.display_name or "Без имени") for m in members]
    bases = [v if len(v) <= 40 else v[:37] + "…" for v in bases]
    counts = Counter(n.casefold() for n in bases)
    seen: Counter[str] = Counter()
    letters = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ"
    names = {}
    for m, base in zip(members, bases, strict=True):
        key = base.casefold()
        i = seen[key]
        seen[key] += 1
        suffix = (
            (" · " + (letters[i] if i < len(letters) else str(i + 1)))
            if counts[key] > 1
            else ""
        )
        names[m.user_id] = base + suffix
    if len({v.casefold() for v in names.values()}) != len(names):
        # A typed name may itself look like a generated alias. Prefix every row
        # with its group-local letter in that rare case; never expose an ID.
        names = {
            m.user_id: f"{letters[i] if i < len(letters) else i + 1} · {base}"
            for i, (m, base) in enumerate(zip(members, bases, strict=True))
        }
    return names


async def roster(
    api: BotApi, actor: int, gid: int, *, first: Page[MemberProfile] | None = None
) -> dict[int, str]:
    members: list[MemberProfile] = []
    page = (
        first
        if first is not None and first.offset == 0
        else await api.members(actor, gid)
    )
    while True:
        members.extend(page.items)
        if len(page.items) < page.limit:
            break
        page = await api.members(actor, gid, offset=page.offset + page.limit)
    return member_names(members)


def person(names: dict[int, str], uid: int) -> str:
    return names.get(uid, "Участник")
