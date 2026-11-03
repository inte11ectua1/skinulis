"""L-03 ui; approved T-06 API only."""

from uuid import uuid4

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import LinkPreviewOptions, Message
from pydantic import SecretStr

from bot.api_client import ApiError, ApiFailure, BotApi
from bot.keyboards import action_keyboard
from bot.presentation import html_card
from bot.states import GroupFlow, Navigation, Onboarding

WELCOME = "Скинулись\nОбщие расходы — без путаницы.\n\nСоздайте профиль, чтобы вести расходы с друзьями. Уже пользовались сервисом? Привяжите прежний аккаунт.\nБанковские переводы вы делаете сами."
HELP = "Как пользоваться\n\n1. Создайте группу и пригласите друзей.\n2. Запишите расход и выберите, кто участвовал.\n3. Посмотрите долги и план переводов.\n4. После оплаты получатель подтверждает получение.\n\nБот учитывает расходы, но не переводит деньги.\n/start — главное меню\n/cancel — отменить несохранённый ввод\n\nЕсли ответ на сохранение потерялся, сначала проверьте историю."


UNAVAILABLE = "Выберите доступное действие в меню."


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
    "link_code_invalid": "Код недействителен, истёк, отозван или уже использован. Получите новый код в аккаунте по почте.",
    "telegram_identity_conflict": "Объединение двух существующих профилей не поддерживается.",
    "telegram_already_linked": "аккаунт по почте уже связан с Telegram. Объединение профилей не поддерживается.",
    "email_profile_required": "Код должен быть получен в вашем существующем email-аккаунте по инструкции подключения.",
    "invite_invalid": "Приглашение недействительно, истекло, использовано или отозвано. Попросите владельца прислать новую ссылку.",
    "already_member": "Вы уже участник этой группы. Откройте «Мои группы».",
    "group_full": "В группе уже 30 участников. Вступить сейчас нельзя.",
    "invite_consumed": "Приглашение уже использовано. Отозвать его нельзя.",
    "owner_required": "Управлять приглашениями может только владелец группы.",
    "request_conflict": "Ключ запроса относится к другим данным. Проверьте свои группы; не создавайте запись с новым ключом вслепую.",
}


def safe_error(error: ApiError) -> str:
    return CODE_MESSAGES.get(error.error_code or "", str(error))


async def reset(state: FSMContext) -> None:
    data = await state.get_data()
    panel = {k: data[k] for k in ("panel_id", "telegram_name", "toast") if k in data}
    await state.clear()
    await state.update_data(**panel)


def pages(text: str, limit: int = 2800) -> list[str]:
    """Bound parsed Telegram text; keep all rows reachable, never truncate amounts."""
    result: list[str] = []
    current = ""
    for row in text.splitlines(keepends=True):
        while len(row) > limit:
            if current:
                result.append(current)
                current = ""
            result.append(row[:limit])
            row = row[limit:]
        if len(current) + len(row) > limit:
            result.append(current)
            current = ""
        current += row
    if current or not result:
        result.append(current)
    return result


async def screen(
    message: Message,
    state: FSMContext,
    text: str,
    actions: list[tuple[str, str]],
    *,
    page: int = 0,
) -> None:
    data = await state.get_data()
    if data.get("toast"):
        text = str(data["toast"]) + "\n\n" + text
        await state.update_data(toast=None)
    chunks = pages(text)
    page = max(0, min(page, len(chunks) - 1))
    shown = chunks[page]
    visible = (
        actions
        if page == len(chunks) - 1
        else [a for a in actions if a[1] in {"home", "ex:cancel"}]
    )
    visible = list(visible)
    if len(chunks) > 1:
        shown += f"\n\nСтраница {page + 1} из {len(chunks)}"
        if page:
            visible.append(("← Назад по тексту", f"ui:page:{page - 1}"))
        if page + 1 < len(chunks):
            visible.append(("Продолжить →", f"ui:page:{page + 1}"))
    nonce = uuid4().hex[:12]
    data = await state.get_data()
    await state.update_data(
        screen=nonce,
        actions=[value for _, value in visible],
        view_page=page,
        view_text=text,
        view_actions=actions,
    )
    rendered = html_card(shown)
    markup = action_keyboard(nonce, [label for label, _ in visible])
    options = LinkPreviewOptions(is_disabled=True)
    panel = data.get("panel_id")
    bot = message.bot
    if isinstance(panel, int) and bot is not None:
        try:
            await bot.edit_message_text(
                rendered,
                chat_id=message.chat.id,
                message_id=panel,
                reply_markup=markup,
                parse_mode="HTML",
                link_preview_options=options,
            )
            return
        except TelegramBadRequest as error:
            if "message is not modified" in error.message.lower():
                return
            if not any(
                v in error.message.lower()
                for v in (
                    "message to edit not found",
                    "message can't be edited",
                    "message_id_invalid",
                )
            ):
                raise
    sent = await message.answer(
        rendered, reply_markup=markup, parse_mode="HTML", link_preview_options=options
    )
    await state.update_data(panel_id=sent.message_id)


async def home(message: Message, state: FSMContext) -> None:
    await reset(state)
    await state.set_state(Navigation.menu)
    await screen(
        message,
        state,
        "Скинулись\nСоберите общие расходы в одном месте.\n\nВыберите группу или начните новую.",
        [
            ("👥 Мои группы", "groups:0"),
            ("＋ Создать группу", "create"),
            ("⏳ Ожидают подтверждения", "st:groups:0"),
            ("👤 Профиль", "profile"),
            ("Помощь", "help"),
        ],
    )


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
    await reset(state)
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
            "Профиль сейчас существует. Это не доказывает результат предыдущей операции. Откройте «Профиль» и проверьте аккаунт; для привязки также проверьте свой прежний аккаунт по инструкции."
        )
        await ready(message, state)
