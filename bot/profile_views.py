"""A human profile; credentials and internal identity never become screen labels."""

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiError, BotApi
from bot.dto import display_name_input
from bot.states import Navigation, ProfileFlow
from bot.ui import safe_error, screen


async def profile_screen(
    message: Message, state: FSMContext, api: BotApi, actor: int
) -> None:
    profile = await api.profile(actor)
    await state.set_state(Navigation.menu)
    await screen(
        message,
        state,
        "Мой профиль\n"
        + (profile.display_name or "Как к вам обращаться?")
        + "\n\n"
        + (
            "Telegram и аккаунт по почте связаны."
            if profile.email
            else "Вход через Telegram — пароль не нужен."
        )
        + "\nИмя видно участникам ваших групп.",
        [("Изменить имя", "profile:rename"), ("← Главное меню", "home")],
    )


async def begin_name(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileFlow.name)
    await screen(
        message,
        state,
        "Ваше имя\nКак вас показывать друзьям?\n\nОт 1 до 64 символов. Фамилия и имя пользователя необязательны.",
        [("← Назад", "profile")],
    )


async def rename_input(message: Message, state: FSMContext, api: BotApi) -> None:
    if message.from_user is None:
        return
    try:
        name = display_name_input(message.text or "")
    except ValueError:
        await screen(
            message,
            state,
            "Проверьте имя\nНужно от 1 до 64 видимых символов без переносов и управляющих знаков.",
            [("← Назад", "profile")],
        )
        return
    try:
        await api.rename_profile(message.from_user.id, name)
    except ApiError as error:
        await screen(
            message, state, safe_error(error), [("Проверить профиль", "profile")]
        )
        return
    await profile_screen(message, state, api, message.from_user.id)
