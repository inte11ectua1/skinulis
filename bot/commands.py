"""Command menu is provisioned only for the verified separate local test bot."""

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    MenuButtonCommands,
    User,
)

from bot.button_theme import LABELS, THEMES

COMMANDS = [
    BotCommand(command=command, description=f"{THEMES[key].icon} {LABELS[key]}")
    for command, key in [
        ("start", "home"),
        ("groups", "groups"),
        ("profile", "profile"),
        ("help", "help"),
        ("cancel", "cancel"),
    ]
]


async def configure_test_menu(bot: Bot, identity: User) -> None:
    if identity.username != "skinulis_testing_bot":
        raise ValueError("Refusing to configure another bot's menu")
    for language in ("", "ru"):
        await bot.set_my_commands(
            commands=COMMANDS,
            scope=BotCommandScopeAllPrivateChats(),
            language_code=language,
        )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
