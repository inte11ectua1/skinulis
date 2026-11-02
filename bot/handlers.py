"""L-03 handlers; approved T-06 API only."""

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message
from pydantic import SecretStr

from bot.actions import dispatch_action
from bot.api_client import ApiError, ApiFailure, BotApi
from bot.dto import valid_capability
from bot.expense_actions import dispatch_expense
from bot.expense_wizard import text_input
from bot.group_views import begin_group, group_name, show_groups
from bot.keyboards import main_menu
from bot.settlement_actions import amount_message, dispatch_settlement
from bot.settlement_views import pending_groups
from bot.states import ExpenseFlow, GroupFlow, Navigation, Onboarding, SettlementFlow
from bot.ui import ACTIVE as ACTIVE
from bot.ui import FAILED as FAILED
from bot.ui import HELP as HELP
from bot.ui import PRIVATE as PRIVATE
from bot.ui import UNAVAILABLE as UNAVAILABLE
from bot.ui import (
    UNCERTAIN,
    UNCERTAIN_KINDS,
    check_profile,
    offer_onboarding,
    ready,
    recover_identity,
    safe_error,
)
from bot.ui import UNKNOWN as UNKNOWN
from bot.ui import WELCOME as WELCOME
from skinulis_logging import Event, emit


async def start(
    message: Message, state: FSMContext, command: CommandObject, api: BotApi
) -> None:
    if await state.get_state() not in (None, Navigation.menu.state):
        await message.answer(ACTIVE)
        return
    if message.from_user is None or message.from_user.id != message.chat.id:
        return
    await state.clear()
    if command.args:
        payload = command.args
        if not payload.startswith("i_") or not valid_capability(payload[2:]):
            await message.answer(
                "Не удалось открыть приглашение. Проверьте ссылку или попросите новую."
            )
            return
        await state.update_data(invite=SecretStr(payload[2:]))
    await check_profile(message, state, api, message.from_user.id)


async def help_command(message: Message) -> None:
    await message.answer(HELP)


async def cancel(message: Message, state: FSMContext, api: BotApi) -> None:
    await state.clear()
    await message.answer(
        "Незавершённый ввод очищен. Сохранённые записи не отменяются. Если ответ на запись был потерян, её результат остаётся неизвестным: сначала проверьте свои данные."
    )
    if message.from_user is not None:
        await check_profile(message, state, api, message.from_user.id)


async def private_message(message: Message) -> None:
    await message.answer(PRIVATE)


async def unknown_message(message: Message) -> None:
    await message.answer(
        "Выберите действие на текущем экране. /help — справка, /cancel — отмена ввода."
    )


async def callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if (
        not isinstance(message, Message)
        or message.chat.type != ChatType.PRIVATE
        or message.chat.id != callback.from_user.id
    ):
        await callback.answer(PRIVATE, show_alert=True)
        return None
    await callback.answer()
    return message


async def menu_help(callback: CallbackQuery) -> None:
    message = await callback_message(callback)
    if message is not None:
        await help_command(message)


async def check_health(callback: CallbackQuery, state: FSMContext, api: BotApi) -> None:
    message = await callback_message(callback)
    if message is None:
        return
    if await state.get_state() not in (None, Navigation.menu.state):
        await message.answer(ACTIVE)
        return
    try:
        await api.health()
    except ApiError as error:
        text = str(error)
    else:
        text = "Сервис доступен. Профиль и права проверяются отдельно."
    await message.answer(text, reply_markup=main_menu())


async def menu_action(callback: CallbackQuery, state: FSMContext, api: BotApi) -> None:
    message = await callback_message(callback)
    if message is None:
        return
    if await state.get_state() not in (None, Navigation.menu.state):
        await message.answer(ACTIVE)
        return
    actor = callback.from_user.id
    try:
        profile = await api.profile(actor)
    except ApiError as error:
        if (
            error.error_code == "telegram_profile_not_found"
            and error.status_code == 404
        ):
            await offer_onboarding(message, state)
        else:
            await message.answer(safe_error(error))
        return
    try:
        action = (callback.data or "").removeprefix("menu:")
        if action == "groups":
            await show_groups(message, state, api, actor)
        elif action == "create":
            await begin_group(message, state)
        elif action == "pending":
            await pending_groups(message, state, api, actor)
        elif action == "profile":
            kind = "Telegram + API" if profile.email else "Telegram-only"
            await message.answer(
                f"Ваш профиль #{profile.id}\nТип: {kind}\nEmail: {profile.email or 'не указан'}\nСлияние/перепривязка аккаунтов не поддерживается.",
                parse_mode=None,
                reply_markup=main_menu(),
            )
        else:
            await message.answer(UNAVAILABLE, reply_markup=main_menu())
    except ApiError as error:
        await message.answer(safe_error(error))


async def current_action(
    callback: CallbackQuery, state: FSMContext, api: BotApi, bot: Bot
) -> None:
    message = await callback_message(callback)
    if message is None:
        return
    data = await state.get_data()
    parts = (callback.data or "").split(":")
    actions = data.get("actions", [])
    if (
        len(parts) != 3
        or parts[1] != data.get("screen")
        or not parts[2].isdigit()
        or not 0 <= int(parts[2]) < len(actions)
    ):
        await message.answer(UNKNOWN)
        return
    action = str(actions[int(parts[2])])
    # Invalidate before dispatch, including errors or Telegram delivery failures.
    await state.update_data(screen=None, actions=[])
    previous = await state.get_state()
    actor = callback.from_user.id
    try:
        if action.startswith("ex:"):
            await dispatch_expense(action, message, state, api, actor, previous)
        elif action.startswith("st:"):
            await dispatch_settlement(action, message, state, api, actor, previous)
        else:
            await dispatch_action(
                action, message, state, api, actor, bot, data, previous
            )
    except ApiError as error:
        await message.answer(
            safe_error(error) + " Используйте /cancel или /start для восстановления."
        )


async def link_code(message: Message, state: FSMContext, api: BotApi) -> None:
    raw = message.text or ""
    if not valid_capability(raw):
        await message.answer(
            "Нужен только одноразовый код из API (43 URL-safe символа). Пароль и JWT сюда не отправляйте. /cancel — отмена."
        )
        return
    if message.from_user is None:
        return
    # The link code is never put into FSM, including failure/timeout branches.
    await state.set_state(GroupFlow.busy)
    try:
        await api.link(message.from_user.id, SecretStr(raw))
    except ApiError as error:
        if error.kind in UNCERTAIN_KINDS or error.kind == ApiFailure.CONFLICT:
            await message.answer(
                UNCERTAIN if error.kind in UNCERTAIN_KINDS else safe_error(error)
            )
            await recover_identity(message, state, api, message.from_user.id)
        else:
            await state.set_state(Onboarding.link_code)
            await message.answer(safe_error(error) + " Пришлите новый код или /cancel.")
    else:
        await message.answer("API подтвердил привязку аккаунта.")
        await ready(message, state)


async def unknown_callback(callback: CallbackQuery) -> None:
    message = await callback_message(callback)
    if message is not None:
        await message.answer(UNKNOWN)


async def on_error(event: ErrorEvent) -> bool:
    emit(Event.BOT_HANDLER_FAILED, level=logging.WARNING)
    try:
        if event.update.callback_query is not None:
            await event.update.callback_query.answer(FAILED, show_alert=True)
        elif (
            event.update.message is not None
            and event.update.message.chat.type == ChatType.PRIVATE
        ):
            await event.update.message.answer(FAILED)
    except TelegramAPIError:
        emit(Event.TELEGRAM_DELIVERY_FAILED, level=logging.WARNING)
    return True


def create_router() -> Router:
    router = Router(name="navigation")
    router.message.register(private_message, F.chat.type != ChatType.PRIVATE)
    router.message.register(start, CommandStart())
    router.message.register(help_command, Command("help"))
    router.message.register(cancel, Command("cancel"))
    router.message.register(link_code, Onboarding.link_code, ~F.text.startswith("/"))
    router.message.register(group_name, GroupFlow.name, ~F.text.startswith("/"))
    router.message.register(
        amount_message, SettlementFlow.amount, F.text, ~F.text.startswith("/")
    )
    router.message.register(
        text_input,
        F.text,
        StateFilter(
            ExpenseFlow.title,
            ExpenseFlow.amount,
            ExpenseFlow.share,
            ExpenseFlow.item_title,
            ExpenseFlow.item_amount,
        ),
        ~F.text.startswith("/"),
    )
    router.message.register(unknown_message)
    router.callback_query.register(menu_help, F.data == "menu:help")
    router.callback_query.register(check_health, F.data == "menu:health")
    router.callback_query.register(
        menu_action,
        F.data.in_({"menu:groups", "menu:create", "menu:pending", "menu:profile"}),
    )
    router.callback_query.register(current_action, F.data.startswith("l3:"))
    router.callback_query.register(unknown_callback)
    router.errors.register(on_error)
    return router
