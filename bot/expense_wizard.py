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
from bot.expense_views import WARNING
from bot.presentation import MODES, money, person, roster
from bot.states import ExpenseFlow
from bot.ui import reset, screen


class DraftSession(BaseModel):
    group_id: int
    members: list[int]
    names: dict[int, str] = Field(default_factory=dict)
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
        try:
            same_intent = draft.business().model_dump_json() == draft.sent_body
        except ValidationError:
            same_intent = False
        if not same_intent:
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
    draft = DraftSession(group_id=gid, members=ids, names=await roster(api, actor, gid))
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
    await reset(state)
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
        "Новый расход\nКак разделим сумму?\n\nПоровну — одна сумма на всех. Указать суммы — своя доля каждому. По позициям — общий чек.",
        [
            ("Поровну", "ex:mode:equal"),
            ("Указать суммы", "ex:mode:custom"),
            ("По позициям", "ex:mode:by_items"),
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
        ExpenseFlow.title.state: "За что заплатили?\nНапример, «Ужин в пятницу». До 120 символов.",
        ExpenseFlow.amount.state: "Общая сумма: от 0.01 до 1000000.00 ₽, например 1250.00. Два знака после точки.",
        ExpenseFlow.item_title.state: "Название позиции (1–120 символов). Чаевые/сервис — отдельные положительные позиции.",
        ExpenseFlow.item_amount.state: "Стоимость позиции, например 700.00. Положительная цена, без процентов, весов и отрицательных скидок.",
        ExpenseFlow.share.state: f"Указать суммы\n{person(draft.names, draft.share_user or 0)}\n\nВведите долю, например 250.00. Можно 0.00.",
    }
    await screen(
        message,
        state,
        prompts[step],
        [
            (
                "Назад",
                "ex:title"
                if step == ExpenseFlow.amount.state
                else "ex:item_title_back"
                if step == ExpenseFlow.item_amount.state
                else "ex:select"
                if step == ExpenseFlow.share.state
                else "ex:review",
            ),
            ("Отмена", "ex:cancel"),
        ],
    )


async def review(message: Message, state: FSMContext, draft: DraftSession) -> None:
    await state.set_state(ExpenseFlow.draft)
    rows = [
        f"Черновик: {draft.title or 'название ещё не задано'}",
        f"{MODES[draft.mode]} · ещё не сохранено",
    ]
    actions = [("Изменить название", "ex:title"), ("Сменить режим", "ex:modes")]
    if draft.mode == "by_items":
        rows += [f"Позиций: {len(draft.items)} из 50"]
        for index, item in enumerate(draft.items[:5]):
            rows += [
                f"{index + 1}. {item.title} · {money(item.amount)}\n"
                + ", ".join(person(draft.names, u) for u in item.participants)
            ]
        if len(draft.items) > 5:
            rows.append(
                f"Ещё позиций: {len(draft.items) - 5}. Откройте список для правки."
            )
        if len(draft.items) < 50:
            actions.append(("Добавить позицию", "ex:item:new"))
        if draft.items:
            actions.append(("Изменить/убрать позицию", "ex:items"))
    else:
        rows += [
            f"Сумма: {money(draft.amount) if draft.amount else 'ещё не указана'}",
            "Выбранные участники: "
            + ", ".join(person(draft.names, u) for u in draft.selected),
        ]
        actions += [
            ("Изменить сумму", "ex:amount"),
            ("Выбрать участников", "ex:select"),
        ]
        if draft.mode == "custom":
            rows += [
                f"{person(draft.names, uid)} · {money(draft.shares[str(uid)]) if str(uid) in draft.shares else 'укажите долю'}"
                for uid in draft.selected
            ]
            actions += [
                (f"Доля · {person(draft.names, uid)}", f"ex:share:{uid}")
                for uid in draft.selected
            ]
    actions += [
        ("Проверить доли", "ex:preview"),
        ("Отменить расход", "ex:cancel"),
    ]
    await screen(
        message,
        state,
        "\n".join(rows)
        + "\n\nПроверьте данные, затем посмотрите итоговые доли."
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
        f"Кто участвовал в {'позиции' if item else 'расходе'}?\nВыбрано: {len(selected)} из {len(draft.members)}\n\nОтметьте нужных людей. Вы можете не включать себя.",
        [
            (
                ("✅ " if uid in selected else "☐ ") + person(draft.names, uid),
                f"ex:toggle:{uid}",
            )
            for uid in draft.members
        ]
        + [
            ("Выбрать всех", "ex:all"),
            ("Снять выбор", "ex:none"),
            ("Готово", "ex:selected"),
            ("Назад", "ex:review"),
            ("Отмена", "ex:cancel"),
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
            "Проверьте поле: название 1–120 видимых символов; сумма вида 1250.00, без пробелов/запятой/знака/округления. Ноль допустим только в долях. /cancel — отмена."
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
