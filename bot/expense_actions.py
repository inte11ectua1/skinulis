"""L-04 confirmation and recovery. Never retry a financial write automatically."""

from typing import Literal, cast
from uuid import UUID, uuid4

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pydantic import ValidationError

from bot.api_client import ApiError, ApiFailure, BotApi
from bot.expense_dto import DRAFT, ReceiptItem
from bot.expense_views import (
    WARNING,
    expense_detail,
    expense_items,
    expense_list,
    snapshot,
)
from bot.expense_wizard import (
    DraftSession,
    begin,
    keep,
    load,
    mode_screen,
    prompt,
    review,
    select,
)
from bot.presentation import money
from bot.states import ExpenseFlow, Navigation
from bot.ui import UNCERTAIN, UNCERTAIN_KINDS, UNKNOWN, reset, safe_error, screen


async def preview(
    message: Message, state: FSMContext, api: BotApi, actor: int, draft: DraftSession
) -> None:
    try:
        body = draft.business()
    except ValidationError:
        await message.answer(
            "Заполните название, сумму и участников. Для чека добавьте хотя бы одну позицию."
        )
        await review(message, state, draft)
        return
    draft.preview_body = None
    await keep(state, draft)
    await state.set_state(ExpenseFlow.busy)
    try:
        result = await api.preview_expense(actor, draft.group_id, body)
    except ApiError as error:
        await message.answer(expense_error(error))
        await review(message, state, draft)
        return
    if result.group_id != draft.group_id or result.split_mode != draft.mode:
        await message.answer("Предпросмотр не подтверждён. Обновите данные.")
        await review(message, state, draft)
        return
    # Do not enable save until every server row has been delivered successfully.
    preview_text = "\n".join(
        ["Проверка расхода · ещё не сохранено", *snapshot(result, draft.names)]
    )
    await state.update_data(
        preview_summary=preview_text,
        preview_details="\n".join(snapshot(result, draft.names, include_items=True)),
    )
    draft.preview_body = body.model_dump_json()
    await keep(state, draft)
    await state.set_state(ExpenseFlow.preview)
    await screen(
        message,
        state,
        preview_text
        + "\n\nВсё верно? Сохраним только после подтверждения."
        + ("\n" + WARNING if draft.expense_id else ""),
        [
            (
                "Сохранить изменения" if draft.expense_id else "Подтвердить расход",
                "ex:save",
            ),
            *(
                [("Позиции чека", "ex:preview_details")]
                if draft.mode == "by_items"
                else []
            ),
            ("Исправить черновик", "ex:review"),
            ("Отменить расход", "ex:cancel"),
        ],
    )


def expense_error(error: ApiError) -> str:
    messages = {
        "validation_error": "Расход не прошёл проверку. Проверьте сумму, участников и доли: вместе они должны составлять сумму расхода.",
        "invalid_participants": "Состав группы изменился. Обновите состав группы и проверьте выбранных потребителей.",
        "expense_author_required": "Изменять или удалять расход может только автор. Владелец группы не может менять чужой расход.",
        "expense_version_conflict": "Расход уже изменился. Перечитайте карточку и начните редактирование заново.",
        "request_conflict": "Этот запрос уже относится к другой записи. Проверьте список расходов. Новый ключ автоматически не создаётся.",
        "request_history_unavailable": "Не удалось найти исходный запрос. Проверьте сохранённые расходы; не создавайте дубль.",
    }
    return messages.get(error.error_code or "", safe_error(error))


async def reconcile_put(
    message: Message, state: FSMContext, api: BotApi, actor: int, draft: DraftSession
) -> None:
    assert draft.expense_id is not None
    await state.set_state(ExpenseFlow.put_uncertain)
    try:
        await api.expense(actor, draft.expense_id)
    except ApiError as error:
        if error.kind not in {ApiFailure.MISSING, ApiFailure.FORBIDDEN}:
            await screen(
                message,
                state,
                UNCERTAIN + " " + expense_error(error),
                [
                    ("Перечитать актуальную версию", "ex:put_check"),
                ],
            )
            return
        await message.answer(
            "Результат правки не установлен. Расход удалён или недоступен."
        )
        await expense_list(message, state, api, actor, draft.group_id)
        return
    await message.answer(
        "Карточка могла измениться. Показываем текущее состояние; прежнюю правку не повторяем. Проверьте её перед новым редактированием."
    )
    await expense_detail(message, state, api, actor, draft.expense_id)


async def save(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    draft: DraftSession,
    *,
    replay: bool = False,
) -> None:
    if replay:
        if draft.sent_body is None or draft.request_key is None or draft.expense_id:
            await message.answer(UNKNOWN)
            return
        body = DRAFT.validate_json(draft.sent_body)
    else:
        try:
            body = draft.business()
        except ValidationError:
            await message.answer(
                "Черновик неполон. Получите новый серверный предпросмотр."
            )
            await review(message, state, draft)
            return
        if body.model_dump_json() != draft.preview_body:
            await message.answer("Предпросмотр устарел. Сначала запросите новый.")
            await review(message, state, draft)
            return
        draft.sent_body = body.model_dump_json()
        if draft.expense_id is None and draft.request_key is None:
            draft.request_key = str(uuid4())
        await keep(state, draft)
    await state.set_state(ExpenseFlow.busy)
    try:
        if draft.expense_id is not None:
            assert draft.version is not None
            result = await api.update_expense(
                actor, draft.expense_id, body, draft.version
            )
        else:
            assert draft.request_key is not None
            result = await api.create_expense(
                actor, draft.group_id, body, UUID(draft.request_key)
            )
        if (
            result.expense.group_id != draft.group_id
            or (draft.expense_id is not None and result.expense.id != draft.expense_id)
            or (
                draft.expense_id is None
                and result.expense.client_request_id != UUID(str(draft.request_key))
            )
        ):
            raise ApiError(ApiFailure.UNEXPECTED)
    except ApiError as error:
        if draft.expense_id is not None and (
            error.kind in UNCERTAIN_KINDS or error.kind == ApiFailure.CONFLICT
        ):
            await message.answer(
                UNCERTAIN if error.kind in UNCERTAIN_KINDS else expense_error(error)
            )
            await reconcile_put(message, state, api, actor, draft)
        elif error.kind in UNCERTAIN_KINDS or error.kind == ApiFailure.CONFLICT:
            await state.update_data(
                expense_recovery="post", expense_can_retry=error.kind in UNCERTAIN_KINDS
            )
            await state.set_state(ExpenseFlow.post_uncertain)
            actions = [("Проверить расходы", f"ex:list:{draft.group_id}:0")]
            if error.kind in UNCERTAIN_KINDS:
                actions.insert(0, ("Повторить исходный запрос", "ex:post_retry"))
            await screen(
                message,
                state,
                (
                    UNCERTAIN + " " + expense_error(error)
                    if error.kind in UNCERTAIN_KINDS
                    else expense_error(error)
                )
                + " Не создавайте новую запись. Можно повторить только прежнее действие с теми же данными. Отмена завершит восстановление.",
                actions,
            )
        elif error.kind in {
            ApiFailure.INPUT,
            ApiFailure.AUTH,
            ApiFailure.FORBIDDEN,
            ApiFailure.MISSING,
        }:
            await message.answer(expense_error(error))
            await state.update_data(expense_recovery=None)
            await keep(state, draft, changed=True)
            await review(message, state, draft)
        else:
            await message.answer(expense_error(error))
            await expense_list(message, state, api, actor, draft.group_id)
        return
    await state.update_data(
        toast="Расход сохранён" if not replay else "Исходная запись найдена"
    )
    await reset(state)
    await expense_detail(message, state, api, actor, result.expense.id)


async def remove(message: Message, state: FSMContext, api: BotApi, actor: int) -> None:
    data = await state.get_data()
    eid, version, gid = data["delete_id"], data["delete_version"], data["delete_group"]
    await state.set_state(ExpenseFlow.busy)
    try:
        result = await api.delete_expense(actor, eid, version)
    except ApiError as error:
        if error.kind in UNCERTAIN_KINDS:
            await state.update_data(expense_recovery="delete")
            await state.set_state(ExpenseFlow.delete_uncertain)
            await screen(
                message,
                state,
                UNCERTAIN + " Можно повторить то же удаление или проверить список.",
                [
                    ("Повторить удаление", "ex:remove"),
                    ("Проверить расходы", f"ex:list:{gid}:0"),
                ],
            )
        else:
            await message.answer(expense_error(error))
            await reset(state)
            await expense_detail(message, state, api, actor, eid)
        return
    if result.expense.deleted_at is None:
        await message.answer("Удаление пока не подтверждено. Обновите карточку.")
        await expense_detail(message, state, api, actor, eid)
        return
    await state.update_data(toast="Расход удалён. Подтверждённые переводы сохранены.")
    await reset(state)
    await expense_list(message, state, api, actor, gid)


async def dispatch_expense(
    action: str,
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    previous: str | None,
) -> None:
    parts = action.split(":")
    command = parts[1]
    if command == "recover":
        recovery = await state.get_data()
        if recovery.get("expense_recovery") == "delete":
            await state.set_state(ExpenseFlow.delete_uncertain)
            await screen(
                message,
                state,
                UNCERTAIN
                + " Прежнее действие сохранено. Отмена завершит восстановление.",
                [("Повторить удаление", "ex:remove")],
            )
        elif recovery.get("expense_recovery") == "post":
            await state.set_state(ExpenseFlow.post_uncertain)
            await screen(
                message,
                state,
                UNCERTAIN
                + " Исходное действие сохранено. Сначала проверьте список; отмена завершит восстановление.",
                [("Повторить исходный запрос", "ex:post_retry")]
                if recovery.get("expense_can_retry")
                else [
                    ("Проверить расходы", f"ex:list:{(await load(state)).group_id}:0")
                ],
            )
        else:
            await message.answer(UNKNOWN)
        return
    if command == "list":
        await expense_list(message, state, api, actor, int(parts[2]), int(parts[3]))
        return
    if command == "receipt":
        await expense_items(message, state, api, actor, int(parts[2]))
        return
    if command == "detail":
        await expense_detail(message, state, api, actor, int(parts[2]))
        return
    if command == "new" and previous == Navigation.menu.state:
        await begin(message, state, api, actor, int(parts[2]))
        return
    if command in {"edit", "delete"} and previous == Navigation.menu.state:
        value = await api.expense(actor, int(parts[2]))
        profile = await api.profile(actor)
        if value.payer_id != profile.id or value.deleted_at:
            await message.answer("Изменять расход может только его автор.")
            await expense_detail(message, state, api, actor, value.id)
            return
        await reset(state)
        if command == "edit":
            await state.set_state(ExpenseFlow.edit_confirm)
            actions = [
                (
                    "Продолжить редактирование",
                    f"ex:edit_begin:{value.group_id}:{value.id}",
                )
            ]
        else:
            await state.update_data(
                delete_id=value.id,
                delete_version=value.version,
                delete_group=value.group_id,
            )
            await state.set_state(ExpenseFlow.delete_confirm)
            actions = [("Да, удалить расход", "ex:remove")]
        await screen(
            message,
            state,
            f"{'Изменить' if command == 'edit' else 'Удалить'} свой расход «{value.title}» на {money(value.amount)}?\n"
            + WARNING,
            actions + [("Не менять", f"ex:detail:{value.id}")],
        )
        return
    if command == "edit_begin" and previous == ExpenseFlow.edit_confirm.state:
        await begin(message, state, api, actor, int(parts[2]), eid=int(parts[3]))
        return
    if command == "remove" and previous in {
        ExpenseFlow.delete_confirm.state,
        ExpenseFlow.delete_uncertain.state,
    }:
        await remove(message, state, api, actor)
        return
    data = await state.get_data()
    if "expense_session" not in data:
        await message.answer(UNKNOWN)
        return
    draft = await load(state)
    if command == "post_retry" and previous == ExpenseFlow.post_uncertain.state:
        await save(message, state, api, actor, draft, replay=True)
        return
    if command == "put_check" and previous == ExpenseFlow.put_uncertain.state:
        await reconcile_put(message, state, api, actor, draft)
        return
    if command == "save" and previous == ExpenseFlow.preview.state:
        await save(message, state, api, actor, draft)
        return
    if previous not in {
        ExpenseFlow.mode.state,
        ExpenseFlow.draft.state,
        ExpenseFlow.title.state,
        ExpenseFlow.amount.state,
        ExpenseFlow.participants.state,
        ExpenseFlow.share.state,
        ExpenseFlow.item_title.state,
        ExpenseFlow.item_amount.state,
        ExpenseFlow.preview.state,
    }:
        await message.answer(UNKNOWN)
        return
    if (
        command in {"preview_details", "preview_back"}
        and previous == ExpenseFlow.preview.state
        and draft.preview_body is not None
    ):
        if command == "preview_details":
            await screen(
                message,
                state,
                str(data["preview_details"]),
                [("← К подтверждению", "ex:preview_back"), ("Отмена", "ex:cancel")],
            )
        else:
            await screen(
                message,
                state,
                str(data["preview_summary"])
                + "\n\nВсё верно?"
                + ("\n" + WARNING if draft.expense_id else ""),
                [
                    (
                        "Сохранить изменения"
                        if draft.expense_id
                        else "Подтвердить расход",
                        "ex:save",
                    ),
                    ("Позиции чека", "ex:preview_details"),
                    ("Исправить черновик", "ex:review"),
                    ("Отмена", "ex:cancel"),
                ],
            )
        return
    # Returning from a preview to ANY editing action requires a fresh preview.
    await keep(state, draft, changed=True)
    if command == "cancel":
        await screen(
            message,
            state,
            "Отменить весь черновик? Введённые данные не сохранятся.",
            [
                ("Да, отменить ввод", f"ex:list:{draft.group_id}:0"),
                ("Продолжить ввод", "ex:review"),
            ],
        )
    elif command == "review":
        await review(message, state, draft)
    elif command == "modes":
        await mode_screen(message, state)
    elif command == "mode" and previous == ExpenseFlow.mode.state:
        mode = parts[2]
        if mode not in {"equal", "custom", "by_items"}:
            await message.answer(UNKNOWN)
            return
        draft.mode = cast(Literal["equal", "custom", "by_items"], mode)
        draft.amount, draft.selected, draft.shares, draft.items = "", [], {}, []
        draft.item_title, draft.item_amount, draft.item_selected = "", "", []
        draft.item_index = None
        await keep(state, draft, changed=True)
        if draft.title:
            await review(message, state, draft)
        else:
            await prompt(message, state, ExpenseFlow.title.state, draft)
    elif command in {"title", "amount"}:
        await prompt(
            message,
            state,
            ExpenseFlow.title.state if command == "title" else ExpenseFlow.amount.state,
            draft,
        )
    elif command == "item_title_back":
        await prompt(message, state, ExpenseFlow.item_title.state, draft)
    elif command == "select":
        await select(message, state, draft)
    elif (
        command in {"toggle", "all", "none", "selected"}
        and previous == ExpenseFlow.participants.state
    ):
        item = data.get("select_item") is True
        selected = draft.item_selected if item else draft.selected
        if command == "toggle":
            uid = int(parts[2])
            if uid not in draft.members:
                await message.answer(UNKNOWN)
                return
            if uid in selected:
                selected.remove(uid)
            else:
                selected.append(uid)
        elif command == "all":
            selected[:] = draft.members
        elif command == "none":
            selected.clear()
        if not item:
            draft.shares = {k: v for k, v in draft.shares.items() if int(k) in selected}
        if command == "selected" and selected:
            if item:
                receipt_item = ReceiptItem(
                    title=draft.item_title,
                    amount=draft.item_amount,
                    participants=selected,
                )
                if draft.item_index is None:
                    if len(draft.items) >= 50:
                        await message.answer("Допустимо не более 50 позиций.")
                        await review(message, state, draft)
                        return
                    draft.items.append(receipt_item)
                else:
                    draft.items[draft.item_index] = receipt_item
                draft.item_index = None
                draft.item_title, draft.item_amount, draft.item_selected = "", "", []
            await keep(state, draft, changed=True)
            missing = next(
                (u for u in draft.selected if str(u) not in draft.shares), None
            )
            if draft.mode == "custom" and missing is not None:
                draft.share_user = missing
                await prompt(message, state, ExpenseFlow.share.state, draft)
            else:
                await review(message, state, draft)
        else:
            # Empty confirmation keeps the count on this panel without chat spam.
            await keep(state, draft, changed=True)
            await select(message, state, draft, item=item)
    elif command == "share" and int(parts[2]) in draft.selected:
        draft.share_user = int(parts[2])
        await prompt(message, state, ExpenseFlow.share.state, draft)
    elif command == "items":
        await state.set_state(ExpenseFlow.draft)
        await screen(
            message,
            state,
            "Выберите позицию для правки или удаления из черновика.",
            [
                (f"{i + 1}. {value.title[:35]}", f"ex:item:{i}")
                for i, value in enumerate(draft.items)
            ]
            + [("К черновику", "ex:review")],
        )
    elif command == "item":
        if parts[2] == "new":
            if len(draft.items) >= 50:
                await message.answer("Допустимо не более 50 позиций.")
                await review(message, state, draft)
                return
            draft.item_index = None
            draft.item_title, draft.item_amount, draft.item_selected = "", "", []
        else:
            draft.item_index = int(parts[2])
            old_item = draft.items[draft.item_index]
            draft.item_title, draft.item_amount = old_item.title, old_item.amount
            draft.item_selected = old_item.participants.copy()
        await prompt(message, state, ExpenseFlow.item_title.state, draft)
        if draft.item_index is not None:
            await screen(
                message,
                state,
                "Введите новое название, затем цену и состав, или уберите позицию.",
                [
                    ("Убрать позицию", "ex:drop"),
                    ("Не менять позицию", "ex:review"),
                ],
            )
    elif command == "drop" and draft.item_index is not None:
        draft.items.pop(draft.item_index)
        draft.item_index = None
        await keep(state, draft, changed=True)
        await review(message, state, draft)
    elif command == "preview":
        await preview(message, state, api, actor, draft)
    else:
        await message.answer(UNKNOWN)
