"""Read saved expense snapshots and render server results without money arithmetic."""

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiError, BotApi
from bot.expense_dto import (
    ExpensePreview,
    ExpenseProfile,
    ReceiptExpense,
    ReceiptPreview,
)
from bot.group_views import paging
from bot.presentation import MODES, money, person, roster
from bot.states import ExpenseFlow, Navigation
from bot.ui import reset, safe_error, screen

WARNING = (
    "Подтверждённые компенсации сохраняются. Баланс может измениться вплоть до "
    "обратного долга. Бот не отменяет реальные переводы."
)


async def viewing(state: FSMContext) -> bool:
    recovery = (await state.get_data()).get("expense_recovery")
    if recovery in {"post", "delete"}:
        await state.set_state(
            ExpenseFlow.post_uncertain
            if recovery == "post"
            else ExpenseFlow.delete_uncertain
        )
        return True
    await reset(state)
    await state.set_state(Navigation.menu)
    return False


def snapshot(
    value: ExpensePreview | ExpenseProfile,
    names: dict[int, str] | None = None,
    *,
    include_items: bool = False,
) -> list[str]:
    names = names or {}
    rows = [
        value.title,
        money(value.amount),
        f"Оплатил: {person(names, value.payer_id)}",
        f"{MODES[value.split_mode]}",
        "",
        "Доли участников",
        *[f"{person(names, s.user_id)} · {money(s.amount)}" for s in value.shares],
    ]
    if isinstance(value, (ReceiptExpense, ReceiptPreview)) and include_items:
        for item in value.items:  # Preserve the server's historical order and zeros.
            rows += [f"{item.title} · {money(item.amount)}"]
            rows += [
                f"  {person(names, s.user_id)} · {money(s.amount)}" for s in item.shares
            ]
    return rows


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
    text = "Расходы\n" + (
        "Выберите запись, чтобы посмотреть доли."
        if page.items
        else "Здесь пока нет расходов. Начните с первого общего счёта."
    )
    actions = [
        (f"{e.title[:35]} · {money(e.amount)}", f"ex:detail:{e.id}") for e in page.items
    ]
    actions += paging(page, f"ex:list:{gid}")
    actions += (
        [("К восстановлению запроса", "ex:recover")]
        if pending
        else [
            ("＋ Добавить расход", f"ex:new:{gid}"),
            ("К группе", f"group:{gid}"),
        ]
    )
    await screen(
        message,
        state,
        text,
        actions,
    )


async def expense_detail(
    message: Message, state: FSMContext, api: BotApi, actor: int, eid: int
) -> None:
    pending = await viewing(state)
    try:
        value = await api.expense(actor, eid)
        profile = await api.profile(actor)
        names = await roster(api, actor, value.group_id)
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
    text = "\n".join(snapshot(value, names))
    actions = [
        ("Позиции чека", f"ex:receipt:{eid}"),
        ("Обновить расход", f"ex:detail:{eid}"),
        ("К расходам", f"ex:list:{value.group_id}:0"),
    ]
    if not isinstance(value, ReceiptExpense):
        actions = [a for a in actions if a[1] != f"ex:receipt:{eid}"]
    if pending:
        actions.append(("К восстановлению запроса", "ex:recover"))
    elif value.payer_id == profile.id:
        actions = [
            ("Редактировать", f"ex:edit:{eid}"),
            ("Удалить", f"ex:delete:{eid}"),
        ] + actions
    if not pending:
        actions = (
            [
                ("＋ Добавить ещё", f"ex:new:{value.group_id}"),
                ("К балансу", f"st:balances:{value.group_id}"),
            ]
            + actions
            + [("В группу", f"group:{value.group_id}")]
        )
    await screen(message, state, text, actions)


async def expense_items(
    message: Message, state: FSMContext, api: BotApi, actor: int, eid: int
) -> None:
    value = await api.expense(actor, eid)
    names = await roster(api, actor, value.group_id)
    await screen(
        message,
        state,
        "\n".join(snapshot(value, names, include_items=True)),
        [("← К расходу", f"ex:detail:{eid}")],
    )
