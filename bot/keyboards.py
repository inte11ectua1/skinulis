from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def action_keyboard(nonce: str, labels: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, label in enumerate(labels):
        button = InlineKeyboardButton(text=label, callback_data=f"l3:{nonce}:{index}")
        # Selection rows stay full width; two short secondary controls fit one row.
        if (
            label in {"Снять выбор", "Готово", "Отмена"}
            and rows
            and len(rows[-1]) == 1
            and rows[-1][0].text in {"Выбрать всех", "Назад"}
        ):
            rows[-1].append(button)
        else:
            rows.append([button])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мои группы", callback_data="menu:groups")],
            [InlineKeyboardButton(text="Создать группу", callback_data="menu:create")],
            [
                InlineKeyboardButton(
                    text="Ожидают подтверждения", callback_data="menu:pending"
                )
            ],
            [
                InlineKeyboardButton(text="Профиль", callback_data="menu:profile"),
                InlineKeyboardButton(text="Помощь", callback_data="menu:help"),
            ],
        ]
    )
