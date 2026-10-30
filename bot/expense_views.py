"""Read saved expense snapshots and render server results without money arithmetic."""

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiError, BotApi
from bot.expense_dto import (
    ExpenseMutation,
    ExpensePreview,
    ExpenseProfile,
    ReceiptExpense,
    ReceiptPreview,
)
from bot.group_views import paging
from bot.states import ExpenseFlow, Navigation
from bot.ui import safe_error, screen

WARNING = (
    "Подтверждённые компенсации сохраняются. Баланс может измениться вплоть до "
    "обратного долга. Бот не отменяет реальные переводы."
)
MODES = {"equal": "Поровну", "custom": "Точные суммы", "by_items": "По позициям"}


async def viewing(state: FSMContext) -> bool:
    recovery = (await state.get_data()).get("expense_recovery")
    if recovery in {"post", "delete"}:
        await state.set_state(
            ExpenseFlow.post_uncertain
            if recovery == "post"
            else ExpenseFlow.delete_uncertain
        )
        return True
    await state.clear()
    await state.set_state(Navigation.menu)
    return False


async def lines(message: Message, rows: list[str]) -> None:
    """Bound every Telegram message, including 50 items × 30 selected shares."""
    chunk = ""
    for row in rows:
        # Each row contains only bounded titles, IDs and wire money strings.
        if len(chunk) + len(row) + 1 > 1800:
            await message.answer(chunk, parse_mode=None)
            chunk = ""
        chunk += row + "\n"
    if chunk:
        await message.answer(chunk, parse_mode=None)


def snapshot(value: ExpensePreview | ExpenseProfile) -> list[str]:
    rows = [
        f"Расход: {value.title}",
        f"Группа #{value.group_id}",
        f"Плательщик: участник #{value.payer_id}",
        f"Режим: {MODES[value.split_mode]}",
        f"Всего: {value.amount} ₽ (API)",
        "Итоговые доли API:",
        *[f"#{s.user_id}: {s.amount} ₽" for s in value.shares],
    ]
    if isinstance(value, (ReceiptExpense, ReceiptPreview)):
        for item in value.items:  # Preserve the server's historical order and zeros.
            rows += [f"Позиция {item.position}: {item.title} — {item.amount} ₽"]
            rows += [f"  #{s.user_id}: {s.amount} ₽" for s in item.shares]
    return rows


async def mutation_balances(message: Message, result: ExpenseMutation) -> None:
    if result.balances is not None:
        await lines(
            message,
            ["Пересчитанные балансы из ответа API:"]
            + [f"#{b.user_id}: {b.balance} ₽" for b in result.balances],
        )


async def expense_list(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    gid: int,
    offset: int = 0,
) -> None:
    pending = await viewing(state)
    try:
        page = await api.expenses(actor, gid, offset=offset)
    except ApiError as error:
        await screen(
            message,
            state,
            safe_error(error),
            [
                ("Повторить загрузку", f"ex:list:{gid}:{offset}"),
                ("К восстановлению запроса", "ex:recover")
                if pending
                else ("К группам", "groups:0"),
            ],
        )
        return
    await lines(
        message,
        [f"Расходы группы #{gid}"]
        + [
            f"#{e.id} · {e.title} · {e.amount} ₽ · плательщик #{e.payer_id}"
            for e in page.items
        ],
    )
    actions = [
        (f"Открыть #{e.id} · {e.title[:35]}", f"ex:detail:{e.id}") for e in page.items
    ]
    actions += paging(page, f"ex:list:{gid}")
    actions += (
        [("К восстановлению запроса", "ex:recover")]
        if pending
        else [
            ("Добавить расход", f"ex:new:{gid}"),
            ("К группе", f"group:{gid}"),
        ]
    )
    await screen(
        message,
        state,
        "Выберите расход." if page.items else "На этой странице расходов нет.",
        actions,
    )


async def expense_detail(
    message: Message, state: FSMContext, api: BotApi, actor: int, eid: int
) -> None:
    pending = await viewing(state)
    try:
        value = await api.expense(actor, eid)
        profile = await api.profile(actor)
    except ApiError as error:
        await screen(
            message,
            state,
            safe_error(error),
            [
                ("Перечитать расход", f"ex:detail:{eid}"),
                ("К восстановлению запроса", "ex:recover")
                if pending
                else ("К группам", "groups:0"),
            ],
        )
        return
    if value.deleted_at is not None:
        await screen(
            message,
            state,
            "Расход удалён или недоступен.",
            [("К восстановлению запроса", "ex:recover")]
            if pending
            else [("К группам", "groups:0")],
        )
        return
    await lines(
        message,
        [f"Сохранённый расход #{value.id} · версия {value.version}"] + snapshot(value),
    )
    actions = [
        ("Обновить расход", f"ex:detail:{eid}"),
        ("К расходам", f"ex:list:{value.group_id}:0"),
    ]
    if pending:
        actions.append(("К восстановлению запроса", "ex:recover"))
    elif value.payer_id == profile.id:
        actions = [
            ("Редактировать", f"ex:edit:{eid}"),
            ("Удалить", f"ex:delete:{eid}"),
        ] + actions
    await screen(message, state, "Данные получены из API.", actions)
