from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.button_theme import LABELS, decorate, plain_label


def themed_button(
    label: str, action: str, callback: str, *, colors: bool = True
) -> InlineKeyboardButton:
    text, style = decorate(label, action)
    return InlineKeyboardButton(
        text=text, callback_data=callback, style=style if colors else None
    )


def action_keyboard(
    nonce: str, actions: list[tuple[str, str]], *, colors: bool = True
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    previous = ""
    primary_used = False
    for index, (label, action) in enumerate(actions):
        button = themed_button(label, action, f"l3:{nonce}:{index}", colors=colors)
        if button.style == "primary":
            if primary_used:
                button.style = None
            primary_used = True
        if plain_label(label) in {"Снять выбор", "Отмена"} and previous in {
            "Выбрать всех",
            "Назад",
        }:
            rows[-1].append(button)
        else:
            rows.append([button])
        previous = plain_label(label)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [themed_button(label, action, action)]
            for label, action in [
                (LABELS["groups"], "menu:groups"),
                (LABELS["create"], "menu:create"),
                (LABELS["pending"], "menu:pending"),
                (LABELS["profile"], "menu:profile"),
                (LABELS["help"], "menu:help"),
            ]
        ]
    )
