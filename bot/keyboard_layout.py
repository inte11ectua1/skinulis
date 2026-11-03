"""Compose Telegram rows by meaning, keeping callback order and labels intact."""

import unicodedata
from typing import Literal

from aiogram.types import InlineKeyboardButton

from bot.button_theme import plain_label, theme_for

type Role = Literal["primary", "secondary", "danger", "navigation", "record"]


def role_for(label: str, action: str) -> Role:
    theme = theme_for(label, action)
    if theme in {"delete", "reject"}:
        return "danger"
    if theme in {"back", "home", "cancel", "next"}:
        return "navigation"
    if action.startswith(
        (
            "group:",
            "ex:detail:",
            "st:detail:",
            "st:receiver:",
            "ex:toggle:",
            "ex:share:",
        )
    ):
        return "record"  # Names, checkboxes and saved records need the full width.
    if theme in {
        "new_expense",
        "mark_transfer",
        "preview",
        "confirm",
        "done",
        "create",
    }:
        return "primary"
    if label.startswith("← "):
        return "navigation"
    if action in {"menu:groups", "groups:0"} or theme == "balances":
        return "primary"
    return "secondary"


def compact(text: str) -> bool:
    # Conservative width estimate, not a promise about client pixels. Emoji and
    # wide characters cost two cells; combining marks/variation selectors none.
    width = 0
    for char in text:
        if unicodedata.combining(char) or char in "\ufe0f\u200d":
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width <= 20


def pair_group(label: str, action: str, role: Role) -> str:
    if action in {"ex:all", "ex:none"}:
        return "selection-tools"
    if role == "navigation":
        return "navigation"
    if action.startswith("st:list:") and plain_label(label) in {
        "Все состояния",
        "Ожидает",
        "Подтверждено",
        "Отклонено",
        "Отменено",
        "Мне",
        "От меня",
        "Все направления",
    }:
        return (
            "direction"
            if plain_label(label) in {"Мне", "От меня", "Все направления"}
            else "status"
        )
    return "secondary"


def layout(
    actions: list[tuple[str, str]], buttons: list[InlineKeyboardButton]
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    previous_group: str | None = None
    for (label, action), button in zip(actions, buttons, strict=True):
        role = role_for(label, action)
        group = pair_group(label, action, role)
        can_pair = role in {"secondary", "navigation"} and compact(button.text)
        if can_pair and previous_group == group and len(rows[-1]) == 1:
            rows[-1].append(button)
            previous_group = None
        else:
            rows.append([button])
            previous_group = group if can_pair else None
    return rows
