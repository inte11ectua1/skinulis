"""L-03 ui; approved T-06 API only."""

from uuid import uuid4

from aiogram.fsm.context import FSMContext
from aiogram.types import LinkPreviewOptions, Message
from pydantic import SecretStr

from bot.api_client import ApiError, ApiFailure, BotApi
from bot.keyboards import action_keyboard, main_menu
from bot.states import GroupFlow, Navigation, Onboarding

WELCOME = (
    "Привет! Я «Скинулись» — помогу учитывать общие расходы. "
    "Банковские переводы вы делаете сами.\n"
    "Создать Telegram-only профиль или привязать существующий API-аккаунт? "
    "Email и пароль для Telegram-only профиля не нужны. "
    "Пароль, JWT и доступ к email сюда не отправляйте. Объединять два профиля нельзя."
)


HELP = (
    "/start — проверить профиль и открыть меню\n/help — справка\n"
    "/cancel — очистить незавершённый ввод. Сохранённые записи не отменяются.\n"
    "Создайте профиль или привяжите API-аккаунт, затем откройте или создайте группу. "
    "Вступить можно добровольно по одноразовой ссылке владельца. "
    "Расходы и компенсации ещё недоступны. Бот не переводит деньги.\n"
    "После перезапуска черновик теряется. Сначала проверьте профиль/свои группы; "
    "не создавайте запись заново, если результат прежнего запроса неизвестен. "
    "Приглашение откройте повторно по исходной ссылке."
)


UNAVAILABLE = "Расходы и компенсации ещё недоступны."


ACTIVE = "Есть незавершённый ввод. Продолжите его или используйте /cancel."


UNKNOWN = (
    "Эта кнопка больше не действует. Возможно, бот перезапущен и черновик потерян. "
    "Откройте /start или используйте /cancel; сначала проверьте сохранённые записи."
)


PRIVATE = "Откройте личный чат с ботом, чтобы управлять расходами."


FAILED = "Не удалось обработать действие. Попробуйте /start или /cancel."


UNCERTAIN = "Ответ на изменение не подтверждён. Результат пока неизвестен. Сначала проверьте сохранённые данные."


UNCERTAIN_KINDS = {
    ApiFailure.TIMEOUT,
    ApiFailure.NETWORK,
    ApiFailure.SERVER,
    ApiFailure.UNEXPECTED,
}


CODE_MESSAGES = {
    "link_code_invalid": "Код недействителен, истёк, отозван или уже использован. Получите новый код в API-аккаунте.",
    "telegram_identity_conflict": "Объединение двух существующих профилей не поддерживается.",
    "telegram_already_linked": "API-аккаунт уже связан с Telegram. Объединение профилей не поддерживается.",
    "email_profile_required": "Код должен быть получен в вашем существующем email-аккаунте через API.",
    "invite_invalid": "Приглашение недействительно, истекло, использовано или отозвано. Попросите владельца прислать новую ссылку.",
    "already_member": "Вы уже участник этой группы. Откройте «Мои группы».",
    "group_full": "В группе уже 30 участников. Вступить сейчас нельзя.",
    "invite_consumed": "Приглашение уже использовано. Отозвать его нельзя.",
    "owner_required": "Управлять приглашениями может только владелец группы.",
    "request_conflict": "Ключ запроса относится к другим данным. Проверьте свои группы; не создавайте запись с новым ключом вслепую.",
}


def safe_error(error: ApiError) -> str:
    return CODE_MESSAGES.get(error.error_code or "", str(error))


async def screen(
    message: Message, state: FSMContext, text: str, actions: list[tuple[str, str]]
) -> None:
    """Only the current opaque screen can select its server-sourced action."""
    nonce = uuid4().hex[:12]
    await state.update_data(screen=nonce, actions=[value for _, value in actions])
    await message.answer(
        text,
        reply_markup=action_keyboard(nonce, [label for label, _ in actions]),
        parse_mode=None,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def home(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Navigation.menu)
    await message.answer("Что хотите сделать?", reply_markup=main_menu())


async def offer_onboarding(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.choice)
    await screen(
        message,
        state,
        WELCOME,
        [
            ("Создать профиль", "consent"),
            ("Привязать существующий аккаунт", "link"),
            ("Не сейчас", "decline"),
        ],
    )


async def ready(message: Message, state: FSMContext) -> None:
    invite = (await state.get_data()).get("invite")
    await state.clear()
    if isinstance(invite, SecretStr):
        await state.update_data(invite=invite)
        await state.set_state(GroupFlow.join_confirm)
        await screen(
            message,
            state,
            "Вступить в группу по этому приглашению? Название и состав доступны после вступления.",
            [("Вступить", "join"), ("Не вступать", "home")],
        )
    else:
        await home(message, state)


async def check_profile(
    message: Message, state: FSMContext, api: BotApi, actor: int
) -> None:
    try:
        await api.profile(actor)
    except ApiError as error:
        if (
            error.status_code == 404
            and error.error_code == "telegram_profile_not_found"
        ):
            await offer_onboarding(message, state)
        else:
            await state.set_state(Onboarding.uncertain)
            await screen(
                message, state, safe_error(error), [("Проверить профиль", "check")]
            )
    else:
        await ready(message, state)


async def recover_identity(
    message: Message, state: FSMContext, api: BotApi, actor: int
) -> None:
    await state.set_state(Onboarding.uncertain)
    try:
        await api.profile(actor)
    except ApiError:
        await screen(
            message,
            state,
            UNCERTAIN
            + " Профиль пока не подтверждён. Не повторяйте код автоматически.",
            [("Проверить профиль", "identity_recheck")],
        )
    else:
        await message.answer(
            "Профиль сейчас существует. Это не доказывает результат предыдущей операции. Откройте «Профиль» и проверьте аккаунт; для привязки также проверьте /users/me в своём API-аккаунте."
        )
        await ready(message, state)
