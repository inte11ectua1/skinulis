import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.enums import ChatType, MessageEntityType
from aiogram.fsm.context import FSMContext
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import (
    CallbackQuery,
    Chat,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    Update,
    User,
)

from bot.api_client import ApiClient
from bot.handlers import ACTIVE, FAILED, HELP, PRIVATE, UNKNOWN
from bot.keyboards import main_menu
from bot.main import create_dispatcher
from bot.presentation import html_card
from bot.states import Navigation


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class Harness:
    bot: Bot
    dispatcher: Dispatcher
    session: AsyncMock
    api: ApiClient
    requests: list[httpx.Request]
    update_id: int = 0
    actor: int = 123
    last_actions: list[str] = field(default_factory=list)
    last_nonce: str = ""
    last_page: int = 0

    def __post_init__(self) -> None:
        original = self.session.side_effect

        async def response(bot: Bot, method: Any, **kwargs: Any) -> Any:
            result = (
                await original(bot, method, **kwargs) if callable(original) else True
            )
            if isinstance(method, (SendMessage, EditMessageText)) and not isinstance(
                result, Message
            ):
                return Message(
                    message_id=(method.message_id or 1)
                    if isinstance(method, EditMessageText)
                    else 100 + len(self.sent),
                    date=datetime.now(UTC),
                    chat=Chat(
                        id=int(method.chat_id or self.actor), type=ChatType.PRIVATE
                    ),
                    from_user=User(id=bot.id, is_bot=True, first_name="Тестовый бот"),
                    text=method.text,
                    reply_markup=method.reply_markup
                    if isinstance(method.reply_markup, InlineKeyboardMarkup)
                    else None,
                )
            return result

        self.session.side_effect = response

    def action(self, value: str) -> str:
        return f"l3:{self.last_nonce}:{self.last_actions.index(value)}"

    async def sync_screen(self) -> None:
        data = await self.state.get_data()
        self.last_actions = data.get("actions", [])
        self.last_nonce = data.get("screen", "")
        self.last_page = data.get("view_page", 0)

    @property
    def state(self) -> FSMContext:
        return self.dispatcher.fsm.get_context(
            bot=self.bot, chat_id=self.actor, user_id=self.actor
        )

    @property
    def sent(self) -> list[SendMessage]:
        """Rendered screen events, including edits. Raw wire methods stay in session."""
        result = []
        for call in self.session.await_args_list:
            method = call.args[1]
            if (
                isinstance(method, (SendMessage, EditMessageText))
                and method.chat_id == self.actor
            ):
                result.append(
                    SendMessage(
                        chat_id=self.actor,
                        text=method.text or "",
                        reply_markup=method.reply_markup,
                        parse_mode=method.parse_mode,
                    )
                )
        return result

    @property
    def alerts(self) -> list[AnswerCallbackQuery]:
        return [
            call.args[1]
            for call in self.session.await_args_list
            if isinstance(call.args[1], AnswerCallbackQuery) and call.args[1].show_alert
        ]

    def message(self, text: str, *, chat_type: ChatType = ChatType.PRIVATE) -> Message:
        entities = None
        if text.startswith("/"):
            entities = [
                MessageEntity(
                    type=MessageEntityType.BOT_COMMAND,
                    offset=0,
                    length=len(text.split()[0]),
                )
            ]
        return Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=self.actor, type=chat_type),
            from_user=User(id=self.actor, is_bot=False, first_name="Тест"),
            text=text,
            entities=entities,
        )

    async def send(self, text: str, *, chat_type: ChatType = ChatType.PRIVATE) -> None:
        self.update_id += 1
        await self.dispatcher.feed_update(
            self.bot,
            Update(
                update_id=self.update_id,
                message=self.message(text, chat_type=chat_type),
            ),
            api=self.api,
        )

        await self.sync_screen()

    async def click(
        self,
        data: str | None,
        *,
        user_id: int | None = None,
        message: Message | InaccessibleMessage | None = None,
    ) -> None:
        self.update_id += 1
        callback = CallbackQuery(
            id=str(self.update_id),
            from_user=User(
                id=user_id if user_id is not None else self.actor,
                is_bot=False,
                first_name="Тест",
            ),
            chat_instance="test-chat",
            data=data,
            message=message if message is not None else self.message("Меню"),
        )
        await self.dispatcher.feed_update(
            self.bot,
            Update(update_id=self.update_id, callback_query=callback),
            api=self.api,
        )

        await self.sync_screen()


@pytest.fixture
async def harness() -> AsyncIterator[Harness]:
    # Generated at runtime only; not a credential or a committed fake token.
    token = f"{secrets.randbelow(10**8) + 1}:{secrets.token_urlsafe(32)}"
    session = AsyncMock(spec=BaseSession)
    telegram = Bot(token=token, session=session)
    dispatcher = create_dispatcher()
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "database": "ok"})
        if request.url.path == "/internal/users/me":
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "email": None,
                    "telegram_id": 123,
                    "created_at": "2026-10-27T00:00:00Z",
                },
            )
        if request.url.path == "/internal/groups":
            return httpx.Response(200, json={"items": [], "limit": 20, "offset": 0})
        raise AssertionError("Unexpected request")

    transport = httpx.MockTransport(respond)
    from pydantic import SecretStr

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=transport,
    ) as api:
        try:
            yield Harness(telegram, dispatcher, session, api, requests)
        finally:
            await dispatcher.fsm.close()
            await telegram.session.close()


@pytest.mark.anyio
async def test_start_repeat_and_no_false_profile_success(harness: Harness) -> None:
    for _ in range(2):
        await harness.send("/start")
        assert "<b>Скинулись</b>" in harness.sent[-1].text
        assert "Мои группы" in str(harness.sent[-1].reply_markup)
        assert await harness.state.get_state() == Navigation.menu.state
        assert business_state(await harness.state.get_data()) == {}
    combined = " ".join(message.text for message in harness.sent)
    assert "Профиль создан" not in combined
    assert "Вы авторизованы" not in combined
    assert len(harness.requests) == 2
    assert all(request.method == "GET" for request in harness.requests)


@pytest.mark.anyio
async def test_deep_link_is_not_consumed_or_echoed(harness: Harness) -> None:
    payload = secrets.token_urlsafe(24)
    await harness.send("/start " + payload)
    assert "Не удалось открыть приглашение" in harness.sent[-1].text
    assert payload not in harness.sent[-1].text
    assert business_state(await harness.state.get_data()) == {}
    assert not harness.requests


@pytest.mark.anyio
async def test_help_command_and_button_preserve_draft(harness: Harness) -> None:
    await harness.state.set_state("Future:input")
    await harness.state.set_data({"draft": "unsaved"})
    await harness.send("/help")
    assert harness.sent[-1].text == html_card(HELP)
    await harness.click("menu:help")
    assert harness.sent[-1].text == html_card(HELP)
    assert await harness.state.get_state() == "Future:input"
    assert business_state(await harness.state.get_data()) == {"draft": "unsaved"}


@pytest.mark.anyio
async def test_cancel_clears_draft_and_returns_to_menu(harness: Harness) -> None:
    await harness.state.set_state("Future:input")
    await harness.state.set_data({"draft": "unsaved"})
    for _ in range(2):
        await harness.send("/cancel")
        assert await harness.state.get_state() == Navigation.menu.state
        assert business_state(await harness.state.get_data()) == {}
        assert "Мои группы" in str(harness.sent[-1].reply_markup)
        assert "Сохранённые записи" in harness.sent[-2].text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "action", ["menu:groups", "menu:create", "menu:pending", "menu:profile"]
)
async def test_menu_and_repeated_buttons_are_honest(
    harness: Harness, action: str
) -> None:
    await harness.click(action)
    if action == "menu:pending":
        assert "Групп пока нет" in harness.sent[-1].text
    elif action == "menu:create":
        assert "Как назовём" in harness.sent[-1].text
        await harness.click(action)
        assert harness.sent[-1].text == ACTIVE
    elif action == "menu:profile":
        assert "Вход через Telegram" in harness.sent[-1].text
    else:
        assert "пока нет групп" in harness.sent[-1].text
    assert all(request.method == "GET" for request in harness.requests)


@pytest.mark.anyio
async def test_start_and_navigation_do_not_silently_discard_draft(
    harness: Harness,
) -> None:
    await harness.state.set_state("Future:input")
    await harness.state.set_data({"draft": "unsaved"})
    await harness.send("/start")
    await harness.click("menu:groups")
    await harness.click("menu:health")
    assert all(message.text == ACTIVE for message in harness.sent)
    assert business_state(await harness.state.get_data()) == {"draft": "unsaved"}


@pytest.mark.anyio
async def test_unknown_input_and_stale_callback_do_not_echo_secrets(
    harness: Harness,
) -> None:
    private = secrets.token_urlsafe(32)
    await harness.send(private)
    await harness.send("/unknown " + private)
    await harness.click(private)
    await harness.click(None)
    assert harness.sent[-1].text == UNKNOWN
    assert all(private not in message.text for message in harness.sent)
    assert business_state(await harness.state.get_data()) == {}


@pytest.mark.anyio
async def test_group_message_only_redirects_to_private_chat(harness: Harness) -> None:
    await harness.send("/start", chat_type=ChatType.GROUP)
    assert harness.sent[-1].text == PRIVATE
    assert await harness.state.get_state() is None


@pytest.mark.anyio
async def test_foreign_and_inaccessible_callbacks_do_not_change_state(
    harness: Harness,
) -> None:
    await harness.click("menu:health", user_id=456)
    await harness.click(
        "menu:profile",
        message=InaccessibleMessage(
            chat=Chat(id=123, type=ChatType.PRIVATE), message_id=1, date=0
        ),
    )
    assert not harness.sent
    assert await harness.state.get_state() is None
    assert all(
        isinstance(call.args[1], AnswerCallbackQuery)
        for call in harness.session.await_args_list
    )


@pytest.mark.anyio
async def test_service_availability_does_not_authenticate(harness: Harness) -> None:
    await harness.click("menu:health")
    assert "Сервис доступен" in harness.sent[-1].text
    assert "Профиль и права" in harness.sent[-1].text
    assert "Профиль создан" not in harness.sent[-1].text
    assert len(harness.requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500, 502, 503])
async def test_api_error_messages_are_sanitized(harness: Harness, status: int) -> None:
    private = secrets.token_urlsafe(32)
    payload = {
        "error": {
            "code": private,
            "message": "Traceback " + private,
            "request_id": private,
        }
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    async with ApiClient("http://api.test", transport=transport) as api:
        harness.api = api
        await harness.click("menu:health")
    assert private not in harness.sent[-1].text
    assert "Traceback" not in harness.sent[-1].text
    assert "http://" not in harness.sent[-1].text


@pytest.mark.anyio
async def test_unexpected_handler_failure_has_safe_fallback(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    private = secrets.token_urlsafe(32)

    def fail(_: httpx.Request) -> httpx.Response:
        raise RuntimeError(private)

    async with ApiClient("http://api.test", transport=httpx.MockTransport(fail)) as api:
        harness.api = api
        await harness.click("menu:health")
    notice = harness.session.await_args_list[-1].args[1]
    assert isinstance(notice, AnswerCallbackQuery)
    assert notice.text == FAILED
    assert private not in caplog.text
    assert "Traceback" not in caplog.text


def test_keyboard_has_unique_safe_callbacks() -> None:
    buttons = [button for row in main_menu().inline_keyboard for button in row]
    assert {button.text for button in buttons} >= {
        "Мои группы",
        "Создать группу",
        "Ожидают подтверждения",
        "Профиль",
        "Помощь",
    }
    callbacks = [button.callback_data for button in buttons]
    assert len(set(callbacks)) == len(callbacks)
    assert all(data is not None and len(data.encode()) <= 64 for data in callbacks)


def business_state(data: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in data.items()
        if k
        not in {
            "screen",
            "actions",
            "view_text",
            "view_actions",
            "view_page",
            "panel_id",
            "telegram_name",
            "toast",
        }
    }
