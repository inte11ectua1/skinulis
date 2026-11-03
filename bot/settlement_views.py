"""One editable screen per financial view; amounts/order remain server-owned."""

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiError, ApiFailure, BotApi
from bot.group_views import paging
from bot.presentation import STATUSES, money, person, roster
from bot.settlement_dto import (
    Balances,
    Direction,
    Plan,
    SettlementProfile,
    SettlementStatus,
    Transition,
)
from bot.settlement_state import SettlementSession, keep, load
from bot.states import Navigation, SettlementFlow
from bot.ui import reset, safe_error, screen

REAL_MONEY = (
    "Бот не переводит деньги. Подтверждайте только то, что действительно получили."
)
STATUS_TEXT = {
    "pending": "Баланс изменится после подтверждения получателем.",
    "confirmed": "Получатель подтвердил получение — перевод учтён в балансе.",
    "rejected": "Получатель отклонил запись. Баланс не изменился.",
    "cancelled": "Отправитель отменил запись. Баланс не изменился.",
}
ACTION_TEXT = {
    "confirm": "Подтвердить получение",
    "reject": "Отклонить",
    "cancel": "Отменить заявку",
}
TARGET_STATUS = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}


def settlement_error(error: ApiError) -> str:
    return {
        "settlement_balance_conflict": "Долг изменился. Эту сумму сейчас подтвердить нельзя. Запись по-прежнему ожидает: её можно отклонить или отменить.",
        "settlement_state_conflict": "Эта запись уже завершена. Обновите её состояние.",
        "settlement_receiver_required": "Подтвердить или отклонить может только получатель.",
        "settlement_sender_required": "Отменить запись может только её отправитель.",
        "request_conflict": "Этот запрос уже связан с другой записью. Проверьте историю перед новым действием.",
        "invalid_participants": "Выберите другого участника этой группы.",
        "validation_error": "Проверьте сумму и получателя. Например, 500.00; сумма должна быть положительной.",
    }.get(error.error_code or "", safe_error(error))


def menu(gid: int, *, recovering: bool = False) -> list[tuple[str, str]]:
    actions = [
        ("Кто кому должен", f"st:balances:{gid}"),
        ("План переводов", f"st:plan:{gid}"),
        ("Ожидают подтверждения", f"st:list:{gid}:pending:incoming:0"),
        ("История переводов", f"st:list:{gid}:all:all:0"),
    ]
    return actions + (
        [("К восстановлению", "st:recover")]
        if recovering
        else [("Я перевёл деньги", f"st:new:{gid}"), ("← В группу", f"group:{gid}")]
    )


async def viewing(state: FSMContext, gid: int) -> bool:
    data = await state.get_data()
    if "settlement_session" in data:
        session = await load(state)
        if session.group_id == gid and session.recovering:
            await state.set_state(
                SettlementFlow.create_unknown
                if session.uncertain == "create" or session.purpose == "creation"
                else SettlementFlow.transition_unknown
            )
            return True
    await reset(state)
    await state.set_state(Navigation.menu)
    return False


def balance_rows(
    result: Balances, gid: int, names: dict[int, str] | None = None
) -> list[str]:
    if result.group_id != gid:
        raise ApiError(ApiFailure.UNEXPECTED)
    names = names or {}
    return ["Кто кому должен", ""] + [
        f"{person(names, b.user_id)} · "
        + (
            "Долгов нет"
            if b.balance == "0.00"
            else "Нужно вернуть " + money(b.balance.removeprefix("-"))
            if b.balance.startswith("-")
            else "Должны вернуть " + money(b.balance)
        )
        for b in result.balances
    ]


def plan_rows(result: Plan, gid: int, names: dict[int, str] | None = None) -> list[str]:
    if result.group_id != gid:
        raise ApiError(ApiFailure.UNEXPECTED)
    names = names or {}
    return (
        ["План переводов", ""]
        + [
            f"{person(names, t.sender_id)} → {person(names, t.receiver_id)}\n{money(t.amount)}"
            for t in result.transfers
        ]
        + (
            ["Все рассчитались. Переводов не требуется."]
            if not result.transfers
            else []
        )
    )


async def show_balances(
    message: Message, state: FSMContext, api: BotApi, actor: int, gid: int
) -> None:
    recovering = await viewing(state, gid)
    try:
        text = (
            "\n".join(
                balance_rows(
                    await api.balances(actor, gid), gid, await roster(api, actor, gid)
                )
            )
            + "\n\nОжидающие, отклонённые и отменённые записи не меняют долг."
        )
    except ApiError as error:
        text = settlement_error(error)
    await screen(
        message,
        state,
        text,
        [("Обновить", f"st:balances:{gid}")]
        + [a for a in menu(gid, recovering=recovering) if a[1] != f"st:balances:{gid}"],
    )


async def show_plan(
    message: Message, state: FSMContext, api: BotApi, actor: int, gid: int
) -> None:
    recovering = await viewing(state, gid)
    try:
        text = (
            "\n".join(
                plan_rows(
                    await api.settlement_plan(actor, gid),
                    gid,
                    await roster(api, actor, gid),
                )
            )
            + "\n\nЭто рекомендации. Переведите деньги самостоятельно, затем отметьте оплату."
        )
    except ApiError as error:
        text = settlement_error(error)
    await screen(
        message,
        state,
        text,
        [("Обновить", f"st:plan:{gid}")]
        + [a for a in menu(gid, recovering=recovering) if a[1] != f"st:plan:{gid}"],
    )


async def pending_groups(
    message: Message, state: FSMContext, api: BotApi, actor: int, offset: int = 0
) -> None:
    await reset(state)
    await state.set_state(Navigation.menu)
    try:
        page = await api.groups(actor, offset=offset)
    except ApiError as error:
        await screen(
            message,
            state,
            settlement_error(error),
            [("Повторить", f"st:groups:{offset}"), ("← Главное меню", "home")],
        )
        return
    await screen(
        message,
        state,
        "Ожидают подтверждения\nВыберите группу."
        if page.items
        else "Ожидают подтверждения\nГрупп пока нет — создайте свою или примите приглашение.",
        [(g.name[:60], f"st:list:{g.id}:pending:incoming:0") for g in page.items]
        + paging(page, "st:groups")
        + [("← Главное меню", "home")],
    )


async def filters(
    message: Message, state: FSMContext, gid: int, status: str, direction: str
) -> None:
    actions = [("Все состояния", f"st:list:{gid}:all:{direction}:0")] + [
        (label, f"st:list:{gid}:{value}:{direction}:0")
        for value, label in STATUSES.items()
    ]
    actions += [
        (label, f"st:list:{gid}:{status}:{value}:0")
        for value, label in [
            ("incoming", "Мне"),
            ("outgoing", "От меня"),
            ("all", "Все направления"),
        ]
    ]
    await screen(
        message,
        state,
        "Какие переводы показать?\nВыберите состояние или направление.",
        actions + [("← Назад", f"st:list:{gid}:{status}:{direction}:0")],
    )


async def show_list(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    gid: int,
    status: SettlementStatus | None = None,
    direction: Direction = "all",
    offset: int = 0,
) -> None:
    recovering = await viewing(state, gid)
    prefix = f"st:list:{gid}:{status or 'all'}:{direction}"
    try:
        page = await api.settlements(
            actor, gid, status=status, direction=direction, offset=offset
        )
        if any(s.group_id != gid for s in page.items):
            raise ApiError(ApiFailure.UNEXPECTED)
        names = await roster(api, actor, gid)
    except ApiError as error:
        await screen(
            message,
            state,
            settlement_error(error),
            [("Повторить", f"{prefix}:{offset}")] + menu(gid, recovering=recovering),
        )
        return
    session = await load(state) if recovering else None
    actions = [
        (
            f"{STATUSES[s.status]} · {person(names, s.sender_id)} → {person(names, s.receiver_id)} · {money(s.amount)}",
            f"st:detail:{gid}:{s.id}",
        )
        for s in page.items
        if session is None
        or s.id == session.target_id
        or s.client_request_id == session.target_key
    ]
    actions += paging(page, prefix)
    if not recovering:
        actions += [
            ("Фильтры", f"st:filters:{gid}:{status or 'all'}:{direction}"),
            ("Я перевёл деньги", f"st:new:{gid}"),
            ("← В группу", f"group:{gid}"),
        ]
    else:
        actions += [("К восстановлению", "st:recover")]
    text = (
        "Переводы\n"
        + (STATUSES[status] if status else "Все состояния")
        + " · "
        + {"all": "Все направления", "incoming": "Мне", "outgoing": "От меня"}[
            direction
        ]
        + "\n\n"
        + (
            "Откройте запись, чтобы посмотреть детали."
            if page.items
            else "Здесь пока нет переводов. Отметьте оплату только после передачи денег."
        )
    )
    await screen(message, state, text, actions)


def allowed(value: SettlementProfile, user_id: int, action: Transition) -> bool:
    return (
        value.sender_id == user_id
        if action == "cancel"
        else value.receiver_id == user_id
    )


async def show_record(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    value: SettlementProfile,
    session: SettlementSession,
) -> None:
    if value.group_id != session.group_id:
        raise ApiError(ApiFailure.UNEXPECTED)
    profile = await api.profile(actor) if value.status == "pending" else None
    uncertain = session.uncertain == "transition" and value.status == "pending"
    if uncertain:
        await keep(state, session)
        await state.set_state(SettlementFlow.transition_unknown)
    else:
        await reset(state)
        await state.set_state(Navigation.menu)
    names = await roster(api, actor, value.group_id)
    text = f"{STATUSES[value.status]}\n{money(value.amount)}\n\n{person(names, value.sender_id)} → {person(names, value.receiver_id)}\n{STATUS_TEXT[value.status]}"
    if uncertain:
        text += "\n\nОтвет на прежнее действие неизвестен. Допустим только повтор того же действия."
    actions = []
    if profile is not None:
        if uncertain:
            if session.operation and allowed(value, profile.id, session.operation):
                actions.append(("Повторить то же действие", "st:resolve"))
        else:
            for action in ("confirm", "reject", "cancel"):
                if allowed(value, profile.id, action):
                    actions.append(
                        (
                            ACTION_TEXT[action],
                            f"st:ask:{value.group_id}:{value.id}:{action}",
                        )
                    )
    actions += [("Обновить", f"st:detail:{value.group_id}:{value.id}")]
    await screen(
        message,
        state,
        text + "\n\n" + REAL_MONEY,
        actions + menu(value.group_id, recovering=uncertain),
    )
