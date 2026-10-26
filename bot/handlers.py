"""L-02 navigation only; never infer authentication from a button or FSM state."""

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message

from bot.api_client import ApiError, HealthApi
from bot.keyboards import main_menu
from bot.states import Navigation

WELCOME = (
    "Привет! Я «Скинулись» — помогу учитывать общие расходы. "
    "Банковские переводы вы делаете сами.\n"
    "Сейчас доступно стартовое меню. Регистрация и привязка аккаунта пока недоступны; "
    "профиль этим действием не создаётся. Пароль сюда отправлять не нужно."
)
HELP = (
    "«Скинулись» — сервис учёта общих расходов. Бот не переводит деньги.\n"
    "/start — открыть стартовое меню\n"
    "/help — эта справка\n"
    "/cancel — очистить незавершённый ввод и вернуться в меню\n"
    "Регистрация, группы, расходы и компенсации ещё недоступны. "
    "После перезапуска незавершённый ввод может потеряться."
)
UNAVAILABLE = (
    "Эта функция пока недоступна. Она появится после подключения соответствующего API. "
    "Регистрация этим действием не выполняется."
)
ACTIVE = (
    "Есть незавершённый ввод. Чтобы отменить его и открыть меню, используйте /cancel."
)
UNKNOWN = "Эта кнопка больше не действует. Откройте /start или используйте /cancel."
PRIVATE = "Откройте личный чат с ботом, чтобы управлять расходами."
FAILED = "Не удалось обработать действие. Попробуйте /start или /cancel."
logger = logging.getLogger(__name__)


async def enter_menu(state: FSMContext) -> bool:
    if await state.get_state() not in (None, Navigation.menu.state):
        return False
    await state.set_state(Navigation.menu)
    return True


async def start(message: Message, state: FSMContext, command: CommandObject) -> None:
    if not await enter_menu(state):
        await message.answer(ACTIVE)
        return
    text = WELCOME
    if command.args:
        # TODO(UQ-02): approved deep-link parsing/join; never echo or retain payload.
        text += "\nПриглашения пока недоступны. Откройте ссылку после их подключения."
    await message.answer(text, reply_markup=main_menu())


async def help_command(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu())


async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Navigation.menu)
    await message.answer(
        "Незавершённый ввод очищен. Стартовое меню. "
        "Сохранённые записи этой командой не отменяются.",
        reply_markup=main_menu(),
    )


async def private_message(message: Message) -> None:
    await message.answer(PRIVATE)


async def unknown_message(message: Message) -> None:
    # Do not echo arbitrary text: it may contain a code, password or token.
    await message.answer(
        "Выберите действие в меню или используйте /help и /cancel.",
        reply_markup=main_menu(),
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


async def menu_action(callback: CallbackQuery, state: FSMContext) -> None:
    message = await callback_message(callback)
    if message is None:
        return
    if not await enter_menu(state):
        await message.answer(ACTIVE)
        return
    # TODO(UQ-01/02/05/08): no profile/group/pending HTTP contracts in L-02.
    await message.answer(UNAVAILABLE, reply_markup=main_menu())


async def menu_help(callback: CallbackQuery) -> None:
    message = await callback_message(callback)
    if message is not None:
        await message.answer(HELP, reply_markup=main_menu())


async def check_health(
    callback: CallbackQuery, state: FSMContext, api: HealthApi
) -> None:
    message = await callback_message(callback)
    if message is None:
        return
    if not await enter_menu(state):
        await message.answer(ACTIVE)
        return
    try:
        await api.health()
    except ApiError as error:
        text = str(error)
    else:
        text = "Сервис доступен. Регистрация и работа с группами пока недоступны."
    await message.answer(text, reply_markup=main_menu())


async def unknown_callback(callback: CallbackQuery) -> None:
    message = await callback_message(callback)
    if message is not None:
        await message.answer(UNKNOWN)


async def on_error(event: ErrorEvent) -> bool:
    # Never log event/update, exception text, raw URL, tokens or traceback.
    logger.warning("Bot action failed")
    try:
        if event.update.callback_query is not None:
            await event.update.callback_query.answer(FAILED, show_alert=True)
        elif (
            event.update.message is not None
            and event.update.message.chat.type == ChatType.PRIVATE
        ):
            await event.update.message.answer(FAILED)
    except TelegramAPIError:
        logger.warning("Bot could not deliver error notice")
    return True


def create_router() -> Router:
    router = Router(name="navigation")
    router.message.register(private_message, F.chat.type != ChatType.PRIVATE)
    router.message.register(start, CommandStart())
    router.message.register(help_command, Command("help"))
    router.message.register(cancel, Command("cancel"))
    router.message.register(unknown_message)
    router.callback_query.register(menu_help, F.data == "menu:help")
    router.callback_query.register(check_health, F.data == "menu:health")
    router.callback_query.register(
        menu_action,
        F.data.in_({"menu:groups", "menu:create", "menu:pending", "menu:profile"}),
    )
    router.callback_query.register(unknown_callback)
    router.errors.register(on_error)
    return router
