"""Read-only M4 screens. Exact server strings/order, no financial arithmetic."""

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiError, ApiFailure, BotApi
from bot.expense_views import lines
from bot.group_views import paging
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
from bot.ui import safe_error, screen

REAL_MONEY = "Бот не переводит деньги и не проверяет банк. Подтверждайте только реально полученные деньги."
STATUS_TEXT = {
    "pending": "ожидает получателя; баланс не меняется",
    "confirmed": "получатель подтвердил; учтено в балансе",
    "rejected": "получатель отклонил; не влияет на баланс",
    "cancelled": "отправитель отменил заявку; не влияет на баланс",
}
ACTION_TEXT = {
    "confirm": "Подтвердить получение",
    "reject": "Отклонить",
    "cancel": "Отменить заявку",
}
TARGET_STATUS = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}


def settlement_error(error: ApiError) -> str:
    messages = {
        "settlement_balance_conflict": "Долг или доступный кредит изменился. Прежнюю сумму сейчас принять нельзя. При отказе confirm запись остаётся pending: получатель может отклонить, отправитель — отменить заявку. Сумму автоматически не исправляем.",
        "settlement_state_conflict": "Запись уже перешла в конечный статус. Перечитайте актуальное состояние; изменить terminal-статус нельзя.",
        "settlement_receiver_required": "Подтвердить или отклонить может только получатель. Владелец группы не получает дополнительных прав.",
        "settlement_sender_required": "Отменить заявку может только её отправитель.",
        "request_conflict": "UUID относится к другому намерению. Проверьте историю переводов; новый ключ автоматически не создаётся.",
        "invalid_participants": "Получатель должен быть другим участником этой группы. Обновите состав и проверьте выбор.",
        "validation_error": "API не принял данные. Нужна положительная сумма вида 500.00 и другой участник группы. Диапазон BIGINT и текущие долги проверяет API; лимит расхода здесь не применяется.",
    }
    return messages.get(error.error_code or "", safe_error(error))


def menu(gid: int, *, recovering: bool = False) -> list[tuple[str, str]]:
    actions = [
        ("Балансы", f"st:balances:{gid}"),
        ("План переводов", f"st:plan:{gid}"),
        ("Ожидают подтверждения", f"st:list:{gid}:pending:incoming:0"),
        ("Исходящие переводы", f"st:list:{gid}:all:outgoing:0"),
        ("История переводов", f"st:list:{gid}:all:all:0"),
    ]
    return actions + (
        [("К восстановлению заявки", "st:recover")]
        if recovering
        else [
            ("Я перевёл деньги", f"st:new:{gid}"),
            ("К группе", f"group:{gid}"),
        ]
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
    await state.clear()
    await state.set_state(Navigation.menu)
    return False


def balance_rows(result: Balances, gid: int) -> list[str]:
    if result.group_id != gid:
        raise ApiError(ApiFailure.UNEXPECTED)
    return [f"Балансы группы #{gid} (API):"] + [
        f"Участник #{b.user_id}: {b.balance} ₽ — "
        + (
            "долгов нет"
            if b.balance == "0.00"
            else "участник должен"
            if b.balance.startswith("-")
            else "участнику должны"
        )
        for b in result.balances
    ]


def plan_rows(result: Plan, gid: int) -> list[str]:
    if result.group_id != gid:
        raise ApiError(ApiFailure.UNEXPECTED)
    return (
        [f"План переводов группы #{gid} (API):"]
        + [
            f"Участник #{t.sender_id} → Участник #{t.receiver_id}: {t.amount} ₽"
            for t in result.transfers
        ]
        + (["По текущему плану переводов нет."] if not result.transfers else [])
    )


async def show_balances(
    message: Message, state: FSMContext, api: BotApi, actor: int, gid: int
) -> None:
    recovering = await viewing(state, gid)
    try:
        await lines(message, balance_rows(await api.balances(actor, gid), gid))
    except ApiError as error:
        text = settlement_error(error)
    else:
        text = "pending/rejected/cancelled не меняют баланс. Значения получены от API."
    await screen(
        message,
        state,
        text,
        [("Обновить балансы", f"st:balances:{gid}")] + menu(gid, recovering=recovering),
    )


async def show_plan(
    message: Message, state: FSMContext, api: BotApi, actor: int, gid: int
) -> None:
    recovering = await viewing(state, gid)
    try:
        await lines(message, plan_rows(await api.settlement_plan(actor, gid), gid))
    except ApiError as error:
        text = settlement_error(error)
    else:
        text = (
            "Это рекомендации, не факт оплаты и не обязательство. Минимальное число переводов не обещается. Просмотр ничего не создаёт. "
            + REAL_MONEY
        )
    await screen(
        message,
        state,
        text,
        [("Обновить план", f"st:plan:{gid}")] + menu(gid, recovering=recovering),
    )


async def refresh_financials(
    message: Message, api: BotApi, actor: int, gid: int
) -> None:
    # Separate API snapshots; do not derive one endpoint's result from the other.
    for kind in ("balances", "plan"):
        try:
            rows = (
                balance_rows(await api.balances(actor, gid), gid)
                if kind == "balances"
                else plan_rows(await api.settlement_plan(actor, gid), gid)
            )
            await lines(message, rows)
        except ApiError as error:
            await message.answer(
                "Не удалось обновить "
                + ("балансы: " if kind == "balances" else "план: ")
                + settlement_error(error)
            )


async def pending_groups(
    message: Message, state: FSMContext, api: BotApi, actor: int, offset: int = 0
) -> None:
    await state.clear()
    await state.set_state(Navigation.menu)
    try:
        page = await api.groups(actor, offset=offset)
    except ApiError as error:
        await screen(
            message,
            state,
            settlement_error(error),
            [("Повторить загрузку", f"st:groups:{offset}"), ("Главное меню", "home")],
        )
        return
    await screen(
        message,
        state,
        "Выберите группу для входящих pending."
        if page.items
        else "На этой странице групп нет.",
        [
            (f"{g.name[:50]} · #{g.id}", f"st:list:{g.id}:pending:incoming:0")
            for g in page.items
        ]
        + paging(page, "st:groups")
        + [("Главное меню", "home")],
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
        if any(item.group_id != gid for item in page.items):
            raise ApiError(ApiFailure.UNEXPECTED)
    except ApiError as error:
        await screen(
            message,
            state,
            settlement_error(error),
            [("Повторить загрузку", f"{prefix}:{offset}")]
            + menu(gid, recovering=recovering),
        )
        return
    await lines(
        message,
        [
            f"Переводы группы #{gid} · статус: {status or 'все'} · направление: {direction}"
        ]
        + [
            f"#{s.id}: #{s.sender_id} → #{s.receiver_id}, {s.amount} ₽ · {s.status} — {STATUS_TEXT[s.status]}"
            for s in page.items
        ],
    )
    context = await load(state) if recovering else None
    actions = [
        (f"Открыть перевод #{s.id}", f"st:detail:{gid}:{s.id}")
        for s in page.items
        if context is None
        or s.id == context.target_id
        or s.client_request_id == context.target_key
    ]
    actions += paging(page, prefix)
    actions += [
        (f"Статус: {label}", f"st:list:{gid}:{value}:{direction}:0")
        for label, value in [
            ("все", "all"),
            ("pending", "pending"),
            ("confirmed", "confirmed"),
            ("rejected", "rejected"),
            ("cancelled", "cancelled"),
        ]
    ]
    actions += [
        (f"Направление: {label}", f"st:list:{gid}:{status or 'all'}:{value}:0")
        for label, value in [
            ("входящие", "incoming"),
            ("исходящие", "outgoing"),
            ("все", "all"),
        ]
    ]
    await screen(
        message,
        state,
        "Выберите запись. Актуальный статус читается через список API."
        if page.items
        else "На этой странице переводов нет.",
        actions + menu(gid, recovering=recovering),
    )


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
    uncertain_pending = session.uncertain == "transition" and value.status == "pending"
    if uncertain_pending:
        await keep(state, session)
        await state.set_state(SettlementFlow.transition_unknown)
    else:
        await state.clear()
        await state.set_state(Navigation.menu)
    await lines(
        message,
        [
            f"Перевод #{value.id} · группа #{value.group_id}",
            f"Участник #{value.sender_id} → Участник #{value.receiver_id}: {value.amount} ₽",
            f"Актуальный статус API: {value.status} — {STATUS_TEXT[value.status]}",
            f"Создан: {value.created_at.isoformat()}",
            f"Завершён: {value.resolved_at.isoformat() if value.resolved_at else 'ещё нет'}",
        ],
    )
    if value.status == "confirmed":
        await refresh_financials(message, api, actor, value.group_id)
    actions: list[tuple[str, str]] = []
    if profile is not None:
        if uncertain_pending:
            if session.operation and allowed(value, profile.id, session.operation):
                actions.append(("Повторить то же действие", "st:resolve"))
        else:
            transitions: tuple[Transition, ...] = ("confirm", "reject", "cancel")
            for action in transitions:
                if allowed(value, profile.id, action):
                    actions.append(
                        (
                            ACTION_TEXT[action],
                            f"st:ask:{value.group_id}:{value.id}:{action}",
                        )
                    )
    actions += [("Обновить статус", f"st:detail:{value.group_id}:{value.id}")]
    await screen(
        message,
        state,
        (
            "Результат прежнего запроса неизвестен; pending — текущий снимок, запрос ещё мог выполняться. Допустим только явный повтор того же перехода. "
            if uncertain_pending
            else ""
        )
        + REAL_MONEY,
        actions + menu(value.group_id, recovering=uncertain_pending),
    )
