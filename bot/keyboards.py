from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.button_theme import LABELS, decorate
from bot.keyboard_layout import layout


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
    buttons: list[InlineKeyboardButton] = []
    primary_used = False
    for index, (label, action) in enumerate(actions):
        button = themed_button(label, action, f"l3:{nonce}:{index}", colors=colors)
        if button.style == "primary":
            if primary_used:
                button.style = None
            primary_used = True
        buttons.append(button)
    return InlineKeyboardMarkup(inline_keyboard=layout(actions, buttons))


def main_menu() -> InlineKeyboardMarkup:
    actions = [
        (LABELS["groups"], "menu:groups"),
        (LABELS["create"], "menu:create"),
        (LABELS["pending"], "menu:pending"),
        (LABELS["profile"], "menu:profile"),
        (LABELS["help"], "menu:help"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=layout(
            actions, [themed_button(label, action, action) for label, action in actions]
        )
    )
