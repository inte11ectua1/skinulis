"""L-06 full vertical: mocked Telegram, actual local HTTP/Uvicorn/PostgreSQL."""

import logging
import secrets
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Update

from app.config import Settings
from bot.api_client import ApiClient, ApiError
from bot.main import create_dispatcher
from bot.settlement_notifications import NOTICE
from bot.states import Navigation
from tests.integration.test_bot_expenses import fill, open_wizard
from tests.integration.test_bot_identity_groups import choose, telegram
from tests.integration.test_bot_identity_groups import local_api as local_api
from tests.unit.test_bot_handlers import Harness

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def duplicate_click(ui: Harness, button: str) -> None:
    ui.update_id += 1
    user = ui.message("").from_user
    assert user is not None
    event = Update(
        update_id=ui.update_id,
        callback_query=CallbackQuery(
            id=str(ui.update_id),
            from_user=user,
            chat_instance="synthetic",
            data=button,
            message=ui.message("Synthetic screen"),
        ),
    )
    for _ in range(2):
        await ui.dispatcher.feed_update(ui.bot, event, api=ui.api)


async def group(ui: Harness, gid: int) -> None:
    await ui.send("/start")
    await ui.click("menu:groups")
    await choose(ui, f"Ресторанная группа · #{gid}")


async def invite(ui: Harness, gid: int) -> str:
    await group(ui, gid)
    await choose(ui, "Приглашения")
    await choose(ui, "Создать приглашение")
    await choose(ui, "Создать приглашение")
    return next(
        m.text.split("?start=i_")[1] for m in reversed(ui.sent) if "?start=i_" in m.text
    )


async def mark(ui: Harness, gid: int, receiver: int, amount: str) -> int:
    await group(ui, gid)
    await choose(ui, "Я перевёл деньги")
    await choose(ui, f"Участник #{receiver}")
    await ui.send(amount)
    old = await choose(ui, "Да, я уже перевёл деньги")
    await ui.click(old)
    return (await ui.api.settlements(ui.actor, gid, direction="outgoing")).items[-1].id


async def test_full_offline_onboarding_link_invite_three_modes_and_settlements(
    local_api: tuple[str, Settings],
    caplog: pytest.LogCaptureFixture,
) -> None:
    base, settings = local_api
    assert base.startswith("http://127.0.0.1:")
    bot, dispatcher = telegram(), create_dispatcher()
    secret_values = [settings.require_bot_service_token()]
    async with (
        ApiClient(base, service_token=settings.bot_service_token) as api,
        httpx.AsyncClient(
            base_url=base,
            trust_env=False,
            timeout=10,
        ) as public,
    ):

        def ui(actor: int) -> Harness:
            return Harness(
                bot,
                dispatcher,
                cast(AsyncMock, bot.session),
                api,
                [],
                actor * 1000,
                actor,
            )

        tim, anton, dasha = ui(123), ui(456), ui(789)
        try:
            with caplog.at_level(logging.DEBUG):
                await tim.send("/start")
                await choose(tim, "Создать профиль")
                with pytest.raises(ApiError) as missing:
                    await api.profile(123)
                assert missing.value.status_code == 404  # Consent has not happened.
                markup = tim.sent[-1].reply_markup
                assert isinstance(markup, InlineKeyboardMarkup)
                button = next(
                    b.callback_data
                    for row in markup.inline_keyboard
                    for b in row
                    if b.text == "Да, создать"
                )
                assert button is not None
                await duplicate_click(tim, button)
                tim_id = (await api.profile(123)).id
                assert await tim.state.get_state() == Navigation.menu.state

                password = secrets.token_urlsafe(32)
                secret_values.append(password)
                registered = await public.post(
                    "/auth/register",
                    json={"email": "anton@example.com", "password": password},
                )
                assert registered.status_code == 201
                login = await public.post(
                    "/auth/login",
                    json={"email": "anton@example.com", "password": password},
                )
                jwt = login.json()["access_token"]
                secret_values.append(jwt)
                issued = await public.post(
                    "/users/me/telegram-link-code",
                    json={},
                    headers={"Authorization": "Bearer " + jwt},
                )
                assert issued.status_code == 201
                code = issued.json()["code"]
                secret_values.append(code)
                await anton.send("/start")
                await choose(anton, "Привязать существующий аккаунт")
                await anton.send(code)
                anton_id = (await api.profile(456)).id
                assert anton_id == registered.json()["id"]
                assert code not in repr(await anton.state.get_data())

                await tim.click("menu:create")
                await tim.send("  Ресторанная группа  ")
                confirm = await choose(tim, "Создать")
                await tim.click(confirm)
                groups = (await api.groups(123)).items
                assert len(groups) == 1
                gid = groups[0].id
                anton_token = await invite(tim, gid)
                secret_values.append(anton_token)
                await anton.send("/start i_" + anton_token)
                await choose(anton, "Вступить")
                dasha_token = await invite(tim, gid)
                secret_values.append(dasha_token)
                await dasha.send("/start i_" + dasha_token)
                assert "Ресторанная группа" not in " ".join(m.text for m in dasha.sent)
                await choose(dasha, "Создать профиль")
                await choose(dasha, "Да, создать")
                await choose(dasha, "Вступить")
                dasha_id = (await api.profile(789)).id
                ids = [tim_id, anton_id, dasha_id]
                assert [m.user_id for m in (await api.members(123, gid)).items] == ids

                # Neutral one-kopeck expenses exercise zero shares without changing restaurant balances.
                await open_wizard(dasha, gid, "equal")
                await dasha.send("Своя копейка")
                await dasha.send("0.01")
                await choose(dasha, f"Участник #{dasha_id}")
                await choose(dasha, "Готово")
                await choose(dasha, "Серверный предпросмотр")
                assert not (await api.expenses(123, gid)).items
                await choose(dasha, "Подтвердить расход")

                await open_wizard(anton, gid, "custom")
                await anton.send("Нулевые доли")
                await anton.send("0.01")
                await choose(anton, "Выбрать всех")
                await choose(anton, "Готово")
                for amount in ["0.00", "0.01", "0.00"]:
                    await anton.send(amount)
                await choose(anton, "Серверный предпросмотр")
                assert len((await api.expenses(123, gid)).items) == 1
                await choose(anton, "Подтвердить расход")

                await open_wizard(tim, gid, "by_items")
                await fill(tim, "by_items", ids)
                await choose(tim, "Серверный предпросмотр")
                assert len((await api.expenses(123, gid)).items) == 2
                old = await choose(tim, "Подтвердить расход")
                await tim.click(old)
                expenses = (await api.expenses(123, gid)).items
                assert (
                    len(expenses) == 3
                    and len({e.client_request_id for e in expenses}) == 3
                )
                assert expenses[-1].amount == "3200.00"
                assert [s.amount for s in expenses[-1].shares] == [
                    "1000.00",
                    "1400.00",
                    "800.00",
                ]
                assert [s.amount for s in expenses[1].shares] == [
                    "0.00",
                    "0.01",
                    "0.00",
                ]
                assert "Сохранённый расход" in " ".join(m.text for m in tim.sent)
                await choose(tim, "К расходам")
                await choose(tim, "Открыть #" + str(expenses[-1].id) + " · Ресторан")

                async def vector() -> list[str]:
                    return [b.balance for b in (await api.balances(123, gid)).balances]

                assert await vector() == ["2200.00", "-1400.00", "-800.00"]
                await group(tim, gid)
                await choose(tim, "Балансы")
                await choose(tim, "План переводов")
                assert [
                    t.amount for t in (await api.settlement_plan(123, gid)).transfers
                ] == ["1400.00", "800.00"]
                sid = await mark(anton, gid, tim_id, "500.00")
                assert await vector() == ["2200.00", "-1400.00", "-800.00"]
                await tim.send("/start")
                await tim.click("menu:pending")
                await choose(tim, f"Ресторанная группа · #{gid}")
                await choose(tim, f"Открыть перевод #{sid}")
                await choose(tim, "Подтвердить получение")
                assert "реально полученные деньги" in tim.sent[-1].text
                refreshed_from = len(tim.sent)
                old = await choose(tim, "Да, деньги получены")
                await tim.click(old)
                assert await vector() == ["1700.00", "-900.00", "-800.00"]
                refreshed = " ".join(m.text for m in tim.sent[refreshed_from:])
                assert "План переводов группы" in refreshed and "1700.00" in refreshed
                current = await api.confirm_settlement(123, sid)
                assert current.settlement.status == "confirmed"
                assert await vector() == ["1700.00", "-900.00", "-800.00"]

                for action, actor in [("reject", tim), ("cancel", anton)]:
                    pending = await mark(anton, gid, tim_id, "100.00")
                    await group(actor, gid)
                    await choose(actor, "История переводов")
                    await choose(actor, f"Открыть перевод #{pending}")
                    await choose(
                        actor, "Отклонить" if action == "reject" else "Отменить заявку"
                    )
                    await choose(
                        actor,
                        "Да, отклонить"
                        if action == "reject"
                        else "Да, отменить заявку",
                    )
                    assert await vector() == ["1700.00", "-900.00", "-800.00"]
                history = await api.settlements(123, gid)
                assert [s.status for s in history.items] == [
                    "confirmed",
                    "rejected",
                    "cancelled",
                ]
                methods = [
                    call.args[1]
                    for call in cast(AsyncMock, bot.session).await_args_list
                ]
                notices = [
                    m
                    for m in methods
                    if isinstance(m, SendMessage) and m.text == NOTICE
                ]
                assert [m.chat_id for m in notices] == [123, 123, 123]
                assert all(
                    m.reply_markup is None and "500.00" not in m.text for m in notices
                )
                for value in secret_values:
                    assert value not in caplog.text
        finally:
            await dispatcher.fsm.close()
            await bot.session.close()
