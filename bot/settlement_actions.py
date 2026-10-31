"""L-05 manual transfer FSM and explicit recovery under the accepted T-08 contract."""

from typing import cast
from uuid import uuid4

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pydantic import ValidationError

from bot.api_client import ApiError, ApiFailure, BotApi
from bot.settlement_dto import (
    Direction,
    SettlementCreate,
    SettlementProfile,
    SettlementStatus,
    Transition,
    amount_input,
)
from bot.settlement_notifications import notify_receiver
from bot.settlement_state import SettlementSession, keep, load
from bot.settlement_views import (
    REAL_MONEY,
    TARGET_STATUS,
    allowed,
    menu,
    pending_groups,
    settlement_error,
    show_balances,
    show_list,
    show_plan,
    show_record,
)
from bot.states import Navigation, SettlementFlow
from bot.ui import UNCERTAIN, UNCERTAIN_KINDS, UNKNOWN, screen


async def choose_receiver(
    message: Message, state: FSMContext, session: SettlementSession
) -> None:
    await keep(state, session)
    await state.set_state(SettlementFlow.receiver)
    await screen(
        message,
        state,
        "Кому вы уже перевели деньги вне приложения? Выберите другого участника. Допустимость суммы проверит API.",
        [(f"Участник #{uid}", f"st:receiver:{uid}") for uid in session.members]
        + [("Отменить ввод", f"st:discard:{session.group_id}")],
    )


async def begin(
    message: Message, state: FSMContext, api: BotApi, actor: int, gid: int
) -> None:
    await api.group(actor, gid)
    profile = await api.profile(actor)
    members: list[int] = []
    offset = 0
    while True:
        page = await api.members(actor, gid, offset=offset)
        members.extend(
            m.user_id
            for m in page.items
            if m.user_id != profile.id and m.user_id not in members
        )
        if len(page.items) < page.limit:
            break
        offset = page.offset + page.limit
    await state.clear()
    session = SettlementSession(group_id=gid, members=members)
    if not members:
        await state.set_state(Navigation.menu)
        await screen(
            message,
            state,
            "Других участников пока нет. Получатель должен отличаться от отправителя.",
            menu(gid),
        )
        return
    await choose_receiver(message, state, session)


async def review(
    message: Message, state: FSMContext, session: SettlementSession
) -> None:
    await keep(state, session)
    await state.set_state(SettlementFlow.review)
    await screen(
        message,
        state,
        f"Проверка введённых данных: вы → Участник #{session.receiver_id}, {session.amount} ₽. "
        "Вы подтверждаете, что уже отправили эти деньги вне приложения? API проверит текущий долг и создаст pending — баланс пока не изменится. "
        + REAL_MONEY,
        [
            ("Да, я уже перевёл деньги", "st:create"),
            ("Изменить сумму", "st:amount"),
            ("Изменить получателя", "st:receivers"),
            ("Отменить ввод", f"st:discard:{session.group_id}"),
        ],
    )


async def amount_prompt(
    message: Message, state: FSMContext, session: SettlementSession
) -> None:
    session.frozen, session.target_key = None, None
    await keep(state, session)
    await state.set_state(SettlementFlow.amount)
    await screen(
        message,
        state,
        "Сколько вы фактически отправили? Положительная сумма с двумя знаками, например 500.00. Частичный перевод допустим. Предел расхода 1000000.00 здесь не применяется; сумму и текущий долг проверяет API.",
        [
            ("Назад к получателю", "st:receivers"),
            ("Отменить ввод", f"st:discard:{session.group_id}"),
        ],
    )


async def amount_message(message: Message, state: FSMContext) -> None:
    session = await load(state)
    try:
        session.amount = amount_input(message.text or "")
    except (ValueError, ValidationError):
        await message.answer(
            "Введите положительную сумму вида 500.00: без знака, пробелов, запятой, экспоненты и округления. /cancel — отмена."
        )
        return
    await review(message, state, session)


async def recovery(
    message: Message, state: FSMContext, session: SettlementSession
) -> None:
    await keep(state, session)
    await state.set_state(
        SettlementFlow.create_unknown
        if session.uncertain == "create" or session.purpose == "creation"
        else SettlementFlow.transition_unknown
    )
    actions = [("Проверить актуальный статус", "st:find:0")]
    if session.uncertain == "create" and session.can_retry:
        actions.append(("Повторить исходную заявку", "st:post_retry"))
    await screen(
        message,
        state,
        UNCERTAIN
        + " UUID и отправленные данные сохранены. POST replay возвращает историю создания, а не текущий статус. /cancel потеряет черновик и не отменит запрос.",
        actions + menu(session.group_id, recovering=True),
    )


async def find_current(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    session: SettlementSession,
    offset: int = 0,
) -> None:
    await keep(state, session)
    await state.set_state(SettlementFlow.search)
    try:
        page = await api.settlements(
            actor, session.group_id, offset=offset, direction=session.direction
        )
        if any(s.group_id != session.group_id for s in page.items):
            raise ApiError(ApiFailure.UNEXPECTED)
        value = next(
            (
                s
                for s in page.items
                if (session.target_id is None or s.id == session.target_id)
                and (
                    session.target_key is None
                    or s.client_request_id == session.target_key
                )
            ),
            None,
        )
        if value is not None:
            if session.purpose == "review":
                await transition_review(message, state, api, actor, value, session)
            else:
                await show_record(message, state, api, actor, value, session)
            return
    except ApiError as error:
        await screen(
            message,
            state,
            "Актуальный статус не прочитан. " + settlement_error(error),
            [("Повторить чтение статуса", f"st:find:{offset}")]
            + (
                [("К восстановлению заявки", "st:recover")]
                if session.recovering
                else [("История переводов", f"st:list:{session.group_id}:all:all:0")]
            ),
        )
        return
    actions = [("Проверить с начала", "st:find:0")]
    if len(page.items) == page.limit:
        actions.append(
            ("Следующая страница поиска", f"st:find:{page.offset + page.limit}")
        )
    actions += (
        [("К восстановлению заявки", "st:recover")]
        if session.recovering
        else [("История переводов", f"st:list:{session.group_id}:all:all:0")]
    )
    await screen(
        message,
        state,
        "На проверенной странице запись не найдена. Это не доказывает отсутствие записи или отказ запроса. Проверяйте следующие страницы; отдельного GET по ID в контракте нет.",
        actions,
    )


async def transition_review(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    value: SettlementProfile,
    session: SettlementSession,
) -> None:
    assert session.operation is not None
    profile = await api.profile(actor)
    if value.status != "pending" or not allowed(value, profile.id, session.operation):
        await message.answer(
            "Переход недоступен для вашей роли или текущего статуса. Показываю актуальную запись."
        )
        session.purpose = "detail"
        await show_record(message, state, api, actor, value, session)
        return
    await keep(state, session)
    await state.set_state(SettlementFlow.transition_confirm)
    text = (
        f"Вы реально получили {value.amount} ₽ от участника #{value.sender_id}? После подтверждения запись нельзя отменить. "
        if session.operation == "confirm"
        else "Отклонить запись? Не подтверждайте деньги, которые не получили. "
        if session.operation == "reject"
        else "Отменить свою pending-заявку? Это не возвращает деньги, отправленные вне приложения. "
    )
    await screen(
        message,
        state,
        text + REAL_MONEY,
        [
            (
                {
                    "confirm": "Да, деньги получены",
                    "reject": "Да, отклонить",
                    "cancel": "Да, отменить заявку",
                }[session.operation],
                "st:resolve",
            ),
            ("Не менять", f"st:detail:{value.group_id}:{value.id}"),
        ],
    )


async def create(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    session: SettlementSession,
    *,
    retry: bool = False,
) -> None:
    if retry:
        if not session.frozen or session.uncertain != "create" or not session.can_retry:
            await message.answer(UNKNOWN)
            return
        draft = SettlementCreate.model_validate_json(session.frozen)
    else:
        if session.receiver_id is None or session.receiver_id not in session.members:
            await message.answer(UNKNOWN)
            return
        draft = SettlementCreate(
            receiver_id=session.receiver_id,
            amount=session.amount,
            client_request_id=uuid4(),
        )
        session.frozen = draft.model_dump_json()
        session.target_key = draft.client_request_id
    session.purpose, session.direction = "creation", "outgoing"
    await keep(state, session)
    await state.set_state(SettlementFlow.busy)
    try:
        result = await api.create_settlement(actor, session.group_id, draft)
        if (
            result.settlement.group_id != session.group_id
            or result.settlement.client_request_id != draft.client_request_id
        ):
            raise ApiError(ApiFailure.UNEXPECTED)
    except ApiError as error:
        if error.kind in UNCERTAIN_KINDS or (
            error.kind == ApiFailure.CONFLICT
            and error.error_code != "settlement_balance_conflict"
        ):
            session.uncertain, session.can_retry = (
                "create",
                error.kind in UNCERTAIN_KINDS,
            )
            await message.answer(
                UNCERTAIN if error.kind in UNCERTAIN_KINDS else settlement_error(error)
            )
            await recovery(message, state, session)
        else:
            session.frozen, session.target_key, session.uncertain = None, None, None
            session.purpose = "detail"
            await message.answer(settlement_error(error))
            await review(message, state, session)
        return
    session.target_id, session.uncertain, session.can_retry = (
        result.settlement.id,
        None,
        False,
    )
    await keep(state, session)
    bot = message.bot
    if bot is not None:
        await notify_receiver(bot, api, actor, result.settlement.id)
    await message.answer(
        "API подтвердил исходное создание заявки. Ответ мог содержать исторический pending; актуальный статус проверяю через список."
    )
    await find_current(message, state, api, actor, session)


async def resolve(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    session: SettlementSession,
) -> None:
    if session.operation is None or session.target_id is None:
        await message.answer(UNKNOWN)
        return
    await keep(state, session)
    await state.set_state(SettlementFlow.busy)
    methods = {
        "confirm": api.confirm_settlement,
        "reject": api.reject_settlement,
        "cancel": api.cancel_settlement,
    }
    try:
        result = await methods[session.operation](actor, session.target_id)
        value = result.settlement
        if (
            value.id != session.target_id
            or value.group_id != session.group_id
            or value.status != TARGET_STATUS[session.operation]
        ):
            raise ApiError(ApiFailure.UNEXPECTED)
    except ApiError as error:
        session.purpose, session.direction = "reconcile", "all"
        session.uncertain = "transition" if error.kind in UNCERTAIN_KINDS else None
        await keep(state, session)
        await message.answer(
            UNCERTAIN if session.uncertain else settlement_error(error)
        )
        await find_current(message, state, api, actor, session)
        return
    session.uncertain, session.purpose = None, "detail"
    await message.answer(
        f"API подтвердил статус {value.status}. Повтор допустимого terminal-перехода не учитывает деньги второй раз."
    )
    await show_record(message, state, api, actor, value, session)


async def dispatch_settlement(
    action: str,
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    previous: str | None,
) -> None:
    parts = action.split(":")
    command = parts[1]
    if command == "groups":
        await pending_groups(message, state, api, actor, int(parts[2]))
    elif command == "balances":
        await show_balances(message, state, api, actor, int(parts[2]))
    elif command == "plan":
        await show_plan(message, state, api, actor, int(parts[2]))
    elif command == "list":
        status = None if parts[3] == "all" else cast(SettlementStatus, parts[3])
        await show_list(
            message,
            state,
            api,
            actor,
            int(parts[2]),
            status,
            cast(Direction, parts[4]),
            int(parts[5]),
        )
    elif command == "new" and previous == Navigation.menu.state:
        await begin(message, state, api, actor, int(parts[2]))
    elif command in {"detail", "ask"}:
        data = await state.get_data()
        session = (
            await load(state)
            if "settlement_session" in data
            else SettlementSession(group_id=int(parts[2]))
        )
        if not session.recovering:
            session = SettlementSession(group_id=int(parts[2]), target_id=int(parts[3]))
        elif session.group_id != int(parts[2]) or (
            session.target_id is not None and session.target_id != int(parts[3])
        ):
            await message.answer(UNKNOWN)
            return
        if command == "ask":
            if previous != Navigation.menu.state:
                await message.answer(UNKNOWN)
                return
            session.operation, session.purpose = cast(Transition, parts[4]), "review"
        elif session.uncertain == "transition":
            session.purpose = "reconcile"
        await find_current(message, state, api, actor, session)
    elif command == "discard":
        await state.clear()
        await show_list(message, state, api, actor, int(parts[2]), direction="outgoing")
    else:
        if "settlement_session" not in await state.get_data():
            await message.answer(UNKNOWN)
            return
        session = await load(state)
        if command == "recover" and session.recovering:
            await recovery(message, state, session)
        elif command == "find":
            await find_current(message, state, api, actor, session, int(parts[2]))
        elif (
            command == "post_retry" and previous == SettlementFlow.create_unknown.state
        ):
            await create(message, state, api, actor, session, retry=True)
        elif command == "resolve" and previous in {
            SettlementFlow.transition_confirm.state,
            SettlementFlow.transition_unknown.state,
        }:
            await resolve(message, state, api, actor, session)
        elif command == "create" and previous == SettlementFlow.review.state:
            await create(message, state, api, actor, session)
        elif previous not in {
            SettlementFlow.receiver.state,
            SettlementFlow.amount.state,
            SettlementFlow.review.state,
        }:
            await message.answer(UNKNOWN)
        elif command == "receivers":
            session.frozen, session.target_key = None, None
            await choose_receiver(message, state, session)
        elif command == "receiver" and int(parts[2]) in session.members:
            session.receiver_id = int(parts[2])
            await amount_prompt(message, state, session)
        elif command == "amount":
            await amount_prompt(message, state, session)
        else:
            await message.answer(UNKNOWN)
