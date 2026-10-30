"""L-04 draft editing. This module handles strings and selections, never money math."""

from typing import Literal

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pydantic import BaseModel, Field, ValidationError

from bot.api_client import BotApi
from bot.expense_dto import (
    DRAFT,
    ExpenseDraft,
    ReceiptItem,
    draft_from_profile,
    money_input,
    title_input,
)
from bot.expense_views import WARNING, lines
from bot.states import ExpenseFlow
from bot.ui import screen


class DraftSession(BaseModel):
    group_id: int
    members: list[int]
    expense_id: int | None = None
    version: int | None = None
    title: str = ""
    mode: Literal["equal", "custom", "by_items"] = "equal"
    amount: str = ""
    selected: list[int] = Field(default_factory=list)
    shares: dict[str, str] = Field(default_factory=dict)
    items: list[ReceiptItem] = Field(default_factory=list)
    item_index: int | None = None
    item_title: str = ""
    item_amount: str = ""
    item_selected: list[int] = Field(default_factory=list)
    share_user: int | None = None
    preview_body: str | None = None
    sent_body: str | None = None
    request_key: str | None = None

    def business(self) -> ExpenseDraft:
        body: dict[str, object] = {"title": self.title, "split_mode": self.mode}
        if self.mode == "by_items":
            body["items"] = [i.model_dump() for i in self.items]
        elif self.mode == "equal":
            body |= {"amount": self.amount, "participants": self.selected}
        else:
            body |= {
                "amount": self.amount,
                "shares": [
                    {"user_id": uid, "amount": self.shares.get(str(uid), "")}
                    for uid in self.selected
                ],
            }
        return DRAFT.validate_python(body)


async def load(state: FSMContext) -> DraftSession:
    return DraftSession.model_validate_json((await state.get_data())["expense_session"])


async def keep(
    state: FSMContext, draft: DraftSession, *, changed: bool = False
) -> None:
    if changed:
        draft.preview_body = None
        draft.sent_body = None
        draft.request_key = None
    await state.update_data(
        expense_session=draft.model_dump_json(), screen=None, actions=[]
    )


async def begin(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    gid: int,
    *,
    eid: int | None = None,
) -> None:
    # Fetch every member page (max30), not just the first20; API rechecks on save.
    await api.group(actor, gid)
    ids: list[int] = []
    offset = 0
    while True:
        page = await api.members(actor, gid, offset=offset)
        ids.extend(m.user_id for m in page.items if m.user_id not in ids)
        if len(page.items) < page.limit:
            break
        offset = page.offset + page.limit
    draft = DraftSession(group_id=gid, members=ids)
    if eid is not None:
        value = await api.expense(actor, eid)
        profile = await api.profile(actor)
        if value.group_id != gid or value.payer_id != profile.id or value.deleted_at:
            await message.answer("Изменять расход может только его автор.")
            return
        original = draft_from_profile(value)
        draft.expense_id, draft.version = eid, value.version
        draft.title, draft.mode = original.title, original.split_mode
        if original.split_mode == "by_items":
            draft.items = original.items
        else:
            draft.amount = original.amount
            draft.selected = [s.user_id for s in value.shares]
            draft.shares = {str(s.user_id): s.amount for s in value.shares}
    await state.clear()
    await keep(state, draft)
    if eid is not None:
        await review(message, state, draft)
    else:
        await mode_screen(message, state)


async def mode_screen(message: Message, state: FSMContext) -> None:
    await state.set_state(ExpenseFlow.mode)
    await screen(
        message,
        state,
        "Как разделить расход? Смена режима очищает сумму, доли и позиции после вашего выбора.",
        [
            ("Поровну — equal", "ex:mode:equal"),
            ("Точные суммы — custom", "ex:mode:custom"),
            ("По позициям — by_items", "ex:mode:by_items"),
            ("К черновику", "ex:review"),
        ],
    )


async def prompt(
    message: Message, state: FSMContext, step: str | None, draft: DraftSession
) -> None:
    assert step is not None
    await keep(state, draft)  # Invalidates buttons before accepting text at a new step.
    await state.set_state(step)
    prompts = {
        ExpenseFlow.title.state: "Название расхода: 1–120 символов, без управляющих/невидимых символов. /cancel — отмена.",
        ExpenseFlow.amount.state: "Общая сумма: от 0.01 до 1000000.00 ₽, например 1250.00. Два знака после точки. Диапазон проверит API.",
        ExpenseFlow.item_title.state: "Название позиции (1–120 символов). Чаевые/сервис — отдельные положительные позиции.",
        ExpenseFlow.item_amount.state: "Стоимость позиции, например 700.00. Положительная цена, без процентов, весов и отрицательных скидок.",
        ExpenseFlow.share.state: f"Доля участника #{draft.share_user}: точная сумма с двумя знаками. Нулевая доля 0.00 допустима.",
    }
    await screen(message, state, prompts[step], [("Назад к черновику", "ex:review")])


async def review(message: Message, state: FSMContext, draft: DraftSession) -> None:
    await state.set_state(ExpenseFlow.draft)
    rows = [
        f"Черновик: {draft.title or 'название ещё не задано'}",
        f"Режим: {draft.mode}",
    ]
    actions = [("Изменить название", "ex:title"), ("Сменить режим", "ex:modes")]
    if draft.mode == "by_items":
        rows += [f"Позиций: {len(draft.items)} / 50. Итог и доли рассчитает API."]
        for index, item in enumerate(draft.items):
            rows += [
                f"{index + 1}. {item.title} — {item.amount} ₽; участники: "
                + ", ".join(f"#{u}" for u in item.participants)
            ]
        if len(draft.items) < 50:
            actions.append(("Добавить позицию", "ex:item:new"))
        if draft.items:
            actions.append(("Изменить/убрать позицию", "ex:items"))
    else:
        rows += [
            f"Общая сумма (ввод): {draft.amount or 'не задана'}",
            "Выбранные участники: " + ", ".join(f"#{u}" for u in draft.selected),
        ]
        actions += [
            ("Изменить сумму", "ex:amount"),
            ("Выбрать участников", "ex:select"),
        ]
        if draft.mode == "custom":
            rows += [
                f"#{uid}: {draft.shares.get(str(uid), 'не введена')} ₽"
                for uid in draft.selected
            ]
            actions += [(f"Доля #{uid}", f"ex:share:{uid}") for uid in draft.selected]
    await lines(message, rows)
    actions += [
        ("Серверный предпросмотр", "ex:preview"),
        ("Отменить расход", "ex:cancel"),
    ]
    await screen(
        message,
        state,
        "Черновик не сохранён. Суммы/совпадение долей/состав проверит сервер."
        + ("\n" + WARNING if draft.expense_id else ""),
        actions,
    )


async def select(
    message: Message, state: FSMContext, draft: DraftSession, *, item: bool = False
) -> None:
    await state.set_state(ExpenseFlow.participants)
    await state.update_data(select_item=item)
    selected = draft.item_selected if item else draft.selected
    await screen(
        message,
        state,
        "Кто участвует? Выберите хотя бы одного; плательщик может не участвовать.",
        [
            (("✓ " if uid in selected else "") + f"Участник #{uid}", f"ex:toggle:{uid}")
            for uid in draft.members
        ]
        + [
            ("Выбрать всех", "ex:all"),
            ("Готово", "ex:selected"),
            ("Назад к черновику", "ex:review"),
        ],
    )


async def text_input(message: Message, state: FSMContext) -> None:
    draft = await load(state)
    step = await state.get_state()
    raw = message.text or ""
    try:
        if step == ExpenseFlow.title.state:
            draft.title = title_input(raw)
        elif step == ExpenseFlow.amount.state:
            draft.amount = money_input(raw)
        elif step == ExpenseFlow.item_title.state:
            draft.item_title = title_input(raw)
        elif step == ExpenseFlow.item_amount.state:
            draft.item_amount = money_input(raw)
        elif step == ExpenseFlow.share.state and draft.share_user in draft.selected:
            draft.shares[str(draft.share_user)] = money_input(raw, zero=True)
        else:
            return
    except (ValueError, ValidationError):
        await message.answer(
            "Проверьте поле: название 1–120 видимых символов; сумма вида 1250.00, без пробелов/запятой/знака/округления. 0.00 допустима только для custom-доли. /cancel — отмена."
        )
        return
    await keep(state, draft, changed=True)
    if (
        step == ExpenseFlow.title.state
        and not draft.amount
        and draft.mode != "by_items"
    ):
        await prompt(message, state, ExpenseFlow.amount.state, draft)
    elif (
        step == ExpenseFlow.title.state and draft.mode == "by_items" and not draft.items
    ):
        await prompt(message, state, ExpenseFlow.item_title.state, draft)
    elif step == ExpenseFlow.amount.state and not draft.selected:
        await select(message, state, draft)
    elif step == ExpenseFlow.item_title.state:
        await prompt(message, state, ExpenseFlow.item_amount.state, draft)
    elif step == ExpenseFlow.item_amount.state:
        await select(message, state, draft, item=True)
    elif step == ExpenseFlow.share.state:
        missing = next((u for u in draft.selected if str(u) not in draft.shares), None)
        if missing is None:
            await review(message, state, draft)
        else:
            draft.share_user = missing
            await prompt(message, state, ExpenseFlow.share.state, draft)
    else:
        await review(message, state, draft)
