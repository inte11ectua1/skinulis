"""Actual loopback HTTP + PostgreSQL 17, mocked Telegram only. No DB in bot code."""

import asyncio
import logging
import secrets
import socket
from collections.abc import AsyncIterator
from threading import Thread
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import uvicorn
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe
from aiogram.types import InlineKeyboardMarkup, User
from pydantic import SecretStr
from sqlalchemy.engine import URL

from app.config import Settings
from app.core.migrate import main as migrate
from app.main import create_app
from bot.api_client import ApiClient, ApiError
from bot.main import create_dispatcher
from tests.unit.test_bot_handlers import Harness

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def local_api(database_url: URL) -> AsyncIterator[tuple[str, Settings]]:
    assert migrate() == 0
    settings = Settings(_env_file=None)
    application = create_app(settings)
    # Reserve the actual port rather than guess an unused one. Access logs off.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(
        uvicorn.Config(
            application, log_config=None, access_log=False, log_level="warning"
        )
    )
    worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    worker.start()
    try:
        async with asyncio.timeout(15):
            while not server.started:
                assert worker.is_alive()
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{listener.getsockname()[1]}", settings
    finally:
        server.should_exit = True
        await asyncio.to_thread(worker.join, 10)
        listener.close()
        assert not worker.is_alive()


async def choose(ui: Harness, label: str) -> str:
    markup = ui.sent[-1].reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    values = [
        b.callback_data
        for row in markup.inline_keyboard
        for b in row
        if b.text == label
    ]
    assert len(values) == 1 and values[0] is not None
    await ui.click(values[0])
    return values[0]


def telegram() -> Bot:
    session = AsyncMock(spec=BaseSession)

    async def respond(bot: Bot, method: Any, **kwargs: Any) -> Any:
        if isinstance(method, GetMe):
            return User(
                id=bot.id,
                is_bot=True,
                first_name="Local",
                username="skinulis_local_test_bot",
            )
        return True

    session.side_effect = respond
    return Bot(
        token=f"{secrets.randbelow(10**8) + 1}:{secrets.token_urlsafe(32)}",
        session=session,
    )


async def test_profile_group_owner_invite_voluntary_join_real_http(
    local_api: tuple[str, Settings], caplog: pytest.LogCaptureFixture
) -> None:
    base_url, settings = local_api
    bot = telegram()
    dispatcher = create_dispatcher()
    async with ApiClient(base_url, service_token=settings.bot_service_token) as api:
        owner = Harness(bot, dispatcher, cast(AsyncMock, bot.session), api, [])
        member = Harness(
            bot,
            dispatcher,
            cast(AsyncMock, bot.session),
            api,
            [],
            update_id=1000,
            actor=456,
        )
        try:
            with caplog.at_level(logging.DEBUG):
                await owner.send("/start")
                with pytest.raises(ApiError) as missing:
                    await api.profile(123)
                assert missing.value.error_code == "telegram_profile_not_found"
                await choose(owner, "Создать профиль")
                await choose(owner, "Да, создать")
                await owner.click("menu:create")
                await owner.send("  Реальная группа  ")
                await choose(owner, "Создать")
                assert "Группа: Реальная группа" in owner.sent[-1].text
                group = (await api.groups(123)).items[0]
                await choose(owner, "Приглашения")
                await choose(owner, "Создать приглашение")
                await choose(owner, "Создать приглашение")
                link_text = next(
                    m.text for m in owner.sent if "https://t.me/" in m.text
                )
                token = link_text.split("?start=i_")[1]
                await member.send("/start i_" + token)
                assert all("Реальная группа" not in m.text for m in member.sent)
                await choose(member, "Создать профиль")
                await choose(member, "Да, создать")
                confirm = await choose(member, "Вступить")
                await member.click(confirm)
                assert (await api.groups(456)).items[0].id == group.id
                members = await api.members(123, group.id)
                assert len(members.items) == 2
                with pytest.raises(ApiError) as forbidden:
                    await api.invites(456, group.id)
                assert forbidden.value.error_code == "owner_required"
                with pytest.raises(ApiError) as consumed:
                    await api.join(456, SecretStr(token))
                assert consumed.value.error_code == "invite_invalid"
                # New invite and explicit revoke via bot/client; no leaked token in list.
                issued = await api.issue_invite(123, group.id, uuid4())
                assert (await api.revoke_invite(123, group.id, issued.id)).revoked_at
                assert token not in caplog.text
                assert settings.require_bot_service_token() not in caplog.text
                assert "X-Telegram-ID" not in caplog.text
        finally:
            await dispatcher.fsm.close()
            await bot.session.close()


async def test_public_code_to_telegram_link_real_http(
    local_api: tuple[str, Settings], caplog: pytest.LogCaptureFixture
) -> None:
    base_url, settings = local_api
    password = secrets.token_urlsafe(32)
    async with httpx.AsyncClient(
        base_url=base_url, trust_env=False, timeout=10
    ) as public:
        registered = await public.post(
            "/auth/register", json={"email": "lera@example.com", "password": password}
        )
        assert registered.status_code == 201
        login = await public.post(
            "/auth/login", json={"email": "lera@example.com", "password": password}
        )
        jwt = login.json()["access_token"]
        headers = {"Authorization": "Bearer " + jwt}
        issued = await public.post(
            "/users/me/telegram-link-code", json={}, headers=headers
        )
        assert issued.status_code == 201
        code = issued.json()["code"]
        bot = telegram()
        dispatcher = create_dispatcher()
        async with ApiClient(base_url, service_token=settings.bot_service_token) as api:
            ui = Harness(bot, dispatcher, cast(AsyncMock, bot.session), api, [])
            try:
                with caplog.at_level(logging.DEBUG):
                    await ui.send("/start")
                    await choose(ui, "Привязать существующий аккаунт")
                    await ui.send(code)
                    profile = await api.profile(123)
                    assert profile.id == registered.json()["id"]
                    me = await public.get("/users/me", headers=headers)
                    assert me.json()["telegram_id"] == 123
                    assert "API подтвердил привязку" in " ".join(
                        m.text for m in ui.sent
                    )
                    assert code not in caplog.text + repr(await ui.state.get_data())
                    assert password not in caplog.text and jwt not in caplog.text
            finally:
                await dispatcher.fsm.close()
                await bot.session.close()
