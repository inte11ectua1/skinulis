"""One current keyboard: edits for callbacks, a fresh bottom card after user text."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject


async def detach(message: Message, panel: int) -> None:
    if message.bot is None:
        return
    try:
        await message.bot.edit_message_reply_markup(
            chat_id=message.chat.id, message_id=panel, reply_markup=None
        )
    except TelegramBadRequest as error:
        if not any(
            t in error.message.lower()
            for t in (
                "message is not modified",
                "message to edit not found",
                "message can't be edited",
                "message_id_invalid",
            )
        ):
            raise
        # Missing/uneditable history cannot be repaired through Bot API. Its nonce
        # is invalidated locally; never delete financial/invite/user history.


async def retire(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    # Disable callbacks even if Telegram is unavailable during cleanup.
    await state.update_data(screen=None, actions=[])
    panel = data.get("panel_id")
    if isinstance(panel, int):
        await detach(message, panel)
    await state.update_data(panel_id=None)


class TextScreenLifecycle(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if (
            not isinstance(event, Message)
            or not isinstance(state, FSMContext)
            or event.from_user is None
            or event.chat.id != event.from_user.id
        ):
            return await handler(event, data)
        previous = await state.get_state()
        saved = (await state.get_data()).get("resume_view")
        if saved and not (event.text or "").startswith("/"):
            # Text can continue the underlying input directly from help. Do not
            # keep a stale return target after the FSM advances to another step.
            await state.update_data(
                resume_view=None,
                view_text=saved[0],
                view_actions=saved[1],
                view_page=saved[2],
            )
        await retire(event, state)
        result = await handler(event, data)
        current = await state.get_data()
        if (
            current.get("panel_id") is None
            and current.get("view_actions")
            and await state.get_state() == previous
        ):
            # Validation/help notices must not strand the surviving draft above
            # the user's new message. No HTTP mutation is retried here.
            from bot.ui import screen

            await screen(
                event,
                state,
                current["view_text"],
                current["view_actions"],
                page=current.get("view_page", 0),
            )
        return result
