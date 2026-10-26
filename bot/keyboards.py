from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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
            [InlineKeyboardButton(text="Профиль", callback_data="menu:profile")],
            [InlineKeyboardButton(text="Помощь", callback_data="menu:help")],
            [
                InlineKeyboardButton(
                    text="Проверить доступность", callback_data="menu:health"
                )
            ],
        ]
    )
