"""Dispatcher → real loopback HTTP → isolated PostgreSQL17. Telegram is mocked."""

import json
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from aiogram.types import InlineKeyboardMarkup

from app.config import Settings
from bot.api_client import ApiClient, ApiError
from bot.dto import GroupDraft
from bot.expense_dto import DRAFT, ReceiptExpense
from bot.main import create_dispatcher
from tests.integration.test_bot_identity_groups import local_api as local_api
from tests.integration.test_bot_identity_groups import telegram
from tests.unit.test_bot_handlers import Harness

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def choose(ui: Harness, label: str) -> str:
    for sent in reversed(ui.sent):
        markup = sent.reply_markup
        if not isinstance(markup, InlineKeyboardMarkup):
            continue
        values = [
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.text == label
        ]
        if values:
            assert len(values) == 1 and values[0] is not None
            await ui.click(values[0])
            return values[0]
    raise AssertionError((label, ui.sent[-1].text))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class LostResponse(httpx.AsyncBaseTransport):
    """Drop one actual API response AFTER commit; never fabricate backend results."""

    def __init__(self) -> None:
        self.http = httpx.AsyncHTTPTransport()
        self.lose: str | None = None
        self.writes: list[tuple[str, str, bytes]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.http.handle_async_request(request)
        if (
            request.method in {"POST", "PUT", "DELETE"}
            and "expense" in request.url.path
        ):
            self.writes.append((request.method, str(request.url), request.content))
            if request.method == self.lose and not request.url.path.endswith(
                "/preview"
            ):
                self.lose = None
                await response.aread()
                await response.aclose()
                raise httpx.ReadTimeout("Test discarded a completed HTTP response")
        return response

    async def aclose(self) -> None:
        await self.http.aclose()


@pytest.fixture
async def finance_ui(
    local_api: tuple[str, Settings],
) -> AsyncIterator[tuple[Harness, LostResponse, list[int], int]]:
    base, settings = local_api
    bot, dispatcher, transport = telegram(), create_dispatcher(), LostResponse()
    async with ApiClient(
        base, service_token=settings.bot_service_token, transport=transport
    ) as api:
        users = [await api.bootstrap(actor) for actor in [123, 456, 789, 999]]
        group = await api.create_group(
            123, GroupDraft(name="Ресторанная группа", client_request_id=uuid4())
        )
        for actor in [456, 789]:
            issued = await api.issue_invite(123, group.id, uuid4())
            assert issued.token is not None
            await api.join(actor, issued.token)
        ui = Harness(bot, dispatcher, cast(AsyncMock, bot.session), api, [])
        try:
            yield ui, transport, [u.id for u in users], group.id
        finally:
            await dispatcher.fsm.close()
            await bot.session.close()


async def open_wizard(ui: Harness, gid: int, mode: str) -> None:
    await ui.send("/start")
    await ui.click("menu:groups")
    await choose(ui, f"Ресторанная группа · #{gid}")
    await choose(ui, "Добавить расход")
    await choose(
        ui,
        {
            "equal": "Поровну — equal",
            "custom": "Точные суммы — custom",
            "by_items": "По позициям — by_items",
        }[mode],
    )


async def fill(ui: Harness, mode: str, ids: list[int]) -> None:
    await ui.send("Ресторан" if mode == "by_items" else "Копейка")
    if mode != "by_items":
        await ui.send("0.01")
        await choose(ui, "Выбрать всех")
        await choose(ui, "Готово")
        if mode == "custom":
            for amount in ["0.01", "0.00", "0.00"]:
                await ui.send(amount)
        return
    for index, (title, amount, consumers) in enumerate(
        [
            ("Паста", "700.00", ids[:1]),
            ("Стейк", "1100.00", ids[1:2]),
            ("Салат", "500.00", ids[2:3]),
            ("Пицца", "900.00", ids[:3]),
        ]
    ):
        if index:
            await choose(ui, "Добавить позицию")
        await ui.send(title)
        await ui.send(amount)
        for uid in consumers:
            await choose(ui, f"Участник #{uid}")
        await choose(ui, "Готово")


@pytest.mark.parametrize("mode", ["equal", "custom", "by_items"])
async def test_real_server_preview_create_author_access_edit_soft_delete(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
    mode: str,
) -> None:
    ui, transport, ids, gid = finance_ui
    await open_wizard(ui, gid, mode)
    await fill(ui, mode, ids)
    assert not (await ui.api.expenses(123, gid)).items
    await choose(ui, "Серверный предпросмотр")
    assert not (await ui.api.expenses(123, gid)).items  # Preview makes no DB record.
    confirm = await choose(ui, "Подтвердить расход")
    await ui.click(confirm)
    saved = (await ui.api.expenses(123, gid)).items
    assert len(saved) == 1
    value = saved[0]
    assert value.payer_id == ids[0] and value.version == 1
    assert [s.amount for s in value.shares] == (
        ["1000.00", "1400.00", "800.00"]
        if mode == "by_items"
        else ["0.01", "0.00", "0.00"]
    )
    if mode == "by_items":
        assert value.amount == "3200.00" and isinstance(value, ReceiptExpense)
        assert [i.title for i in value.items] == ["Паста", "Стейк", "Салат", "Пицца"]
        assert "amount" not in json.loads(
            next(
                body
                for method, url, body in transport.writes
                if method == "POST" and url.endswith("/expenses")
            )
        )
    with pytest.raises(ApiError) as hidden:
        await ui.api.expense(999, value.id)
    assert hidden.value.status_code == 404
    with pytest.raises(ApiError) as forbidden:
        await ui.api.update_expense(
            456,
            value.id,
            DRAFT.validate_python(
                {
                    "title": "Чужая правка",
                    "split_mode": "equal",
                    "amount": "1.00",
                    "participants": [ids[1]],
                }
            ),
            1,
        )
    assert forbidden.value.error_code == "expense_author_required"
    # Full wizard retains original data then replaces mode. Server version is mandatory.
    await choose(ui, "Редактировать")
    assert "обратного долга" in ui.sent[-1].text
    await choose(ui, "Продолжить редактирование")
    await choose(ui, "Сменить режим")
    await choose(ui, "Точные суммы — custom")
    await choose(ui, "Изменить сумму")
    await ui.send("0.01")
    await choose(ui, "Выбрать всех")
    await choose(ui, "Готово")
    for amount in ["0.01", "0.00", "0.00"]:
        await ui.send(amount)
    await choose(ui, "Серверный предпросмотр")
    await choose(ui, "Сохранить изменения")
    current = await ui.api.expense(123, value.id)
    assert current.split_mode == "custom" and current.version == 2
    with pytest.raises(ApiError) as stale:
        await ui.api.delete_expense(123, value.id, 1)
    assert stale.value.error_code == "expense_version_conflict"
    await choose(ui, "Удалить")
    await choose(ui, "Да, удалить расход")
    assert not (await ui.api.expenses(123, gid)).items
    repeated = await ui.api.delete_expense(123, value.id, 2)
    assert repeated.expense.deleted_at and repeated.expense.version == 3


@pytest.mark.parametrize("mutation", ["POST", "PUT", "DELETE"])
async def test_lost_real_response_recovers_without_duplicate_or_stale_retry(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
    mutation: str,
) -> None:
    ui, transport, ids, gid = finance_ui
    await open_wizard(ui, gid, "by_items")
    await fill(ui, "by_items", ids)
    await choose(ui, "Серверный предпросмотр")
    if mutation == "POST":
        transport.lose = "POST"
    await choose(ui, "Подтвердить расход")
    if mutation == "POST":
        await choose(ui, "Проверить расходы")
        await choose(ui, "К восстановлению запроса")
        await choose(ui, "Повторить исходный запрос")
    saved = (await ui.api.expenses(123, gid)).items
    assert len(saved) == 1
    eid = saved[0].id
    if mutation == "PUT":
        await choose(ui, "Редактировать")
        await choose(ui, "Продолжить редактирование")
        await choose(ui, "Изменить название")
        await ui.send("Новая версия")
        await choose(ui, "Серверный предпросмотр")
        transport.lose = "PUT"
        await choose(ui, "Сохранить изменения")
        current = await ui.api.expense(123, eid)
        assert current.version == 2 and current.title == "Новая версия"
        assert len([x for x in transport.writes if x[0] == "PUT"]) == 1
        assert "API подтвердил сохранение изменений" not in " ".join(
            m.text for m in ui.sent
        )
    elif mutation == "DELETE":
        await choose(ui, "Удалить")
        transport.lose = "DELETE"
        await choose(ui, "Да, удалить расход")
        await choose(ui, "Повторить удаление")
        assert not (await ui.api.expenses(123, gid)).items
        repeated = await ui.api.delete_expense(123, eid, 1)
        assert repeated.expense.version == 2
    else:
        posts = [
            x for x in transport.writes if x[0] == "POST" and x[1].endswith("/expenses")
        ]
        assert len(posts) == 2 and posts[0] == posts[1]


async def test_api_rejects_wrong_custom_sum_and_51_items_without_write(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
    local_api: tuple[str, Settings],
) -> None:
    ui, _, ids, gid = finance_ui
    mismatch = DRAFT.validate_python(
        {
            "title": "Неверные доли",
            "split_mode": "custom",
            "amount": "1.00",
            "shares": [{"user_id": ids[0], "amount": "0.00"}],
        }
    )
    with pytest.raises(ApiError) as invalid:
        await ui.api.preview_expense(123, gid, mismatch)
    assert (
        invalid.value.status_code == 400 and not (await ui.api.expenses(123, gid)).items
    )
    # Exercise server's upper item bound as HTTP, independent of the bot shape guard.
    base, settings = local_api
    async with httpx.AsyncClient(base_url=base, trust_env=False) as raw:
        response = await raw.post(
            f"/internal/groups/{gid}/expenses/preview",
            headers={
                "X-Bot-Service-Token": settings.require_bot_service_token(),
                "X-Telegram-ID": "123",
            },
            json={
                "title": "Длинный чек",
                "split_mode": "by_items",
                "items": [{"title": "Чай", "amount": "0.01", "participants": [ids[0]]}]
                * 51,
            },
        )
        assert response.status_code == 400
    assert not (await ui.api.expenses(123, gid)).items
