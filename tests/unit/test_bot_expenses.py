"""Real aiogram Dispatcher/FSM and httpx; both external transports are mocked."""

import ast
import copy
import json
import logging
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import InlineKeyboardMarkup, Update
from pydantic import SecretStr, ValidationError

from bot.api_client import ApiClient
from bot.expense_dto import DRAFT, EXPENSE, PREVIEW, ExpenseMutation
from bot.expense_wizard import keep, load
from bot.main import create_dispatcher
from bot.states import ExpenseFlow
from tests.unit.test_bot_handlers import Harness
from tests.unit.test_bot_onboarding_groups import ContractFixture, error

ROOT = Path(__file__).resolve().parents[2]
O04 = json.loads((ROOT / "docs/finance/fixtures/O-04_EXPENSES.json").read_text("utf-8"))
O05 = json.loads((ROOT / "docs/finance/fixtures/O-05_BY_ITEMS.json").read_text("utf-8"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class ExpenseServer(ContractFixture):
    owner: int = 10
    preview_data: dict[str, Any] = field(
        default_factory=lambda: copy.deepcopy(O05["preview_response"])
    )
    saved: dict[int, dict[str, Any]] = field(default_factory=dict)
    history: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail_after: str | None = None

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if "expense" not in path and path != "/internal/groups/100/members":
            if path == "/internal/groups/100":
                self.requests.append(request)
                return httpx.Response(200, json=self.group(100))
            return super().respond(request)
        self.requests.append(request)
        assert request.headers["X-Telegram-ID"] == "123"
        assert request.headers["X-Bot-Service-Token"]
        assert "authorization" not in request.headers
        if self.overrides.get((method, path)):
            override = self.overrides[method, path].pop(0)
            if isinstance(override, Exception):
                raise override
            return override
        if path.endswith("/members"):
            offset = int(request.url.params["offset"])
            members = [
                {
                    "user_id": uid,
                    "joined_at": "2026-10-28T00:00:00Z",
                    "is_owner": uid == 10,
                }
                for uid in [10, 20, 30]
            ]
            return httpx.Response(
                200,
                json={
                    "items": members[offset : offset + 20],
                    "limit": 20,
                    "offset": offset,
                },
            )
        body = json.loads(request.content) if request.content else {}
        assert not {"payer_id", "author_id", "telegram_id"} & body.keys()
        if path.endswith("/preview"):
            assert "client_request_id" not in body and "expected_version" not in body
            return httpx.Response(200, json=self.preview_data)
        if path == "/internal/groups/100/expenses":
            if method == "GET":
                offset = int(request.url.params["offset"])
                values = [v for v in self.saved.values() if v["deleted_at"] is None]
                return httpx.Response(
                    200,
                    json={
                        "items": values[offset : offset + 20],
                        "limit": 20,
                        "offset": offset,
                    },
                )
            key = body["client_request_id"]
            if key in self.history:
                return httpx.Response(200, json=self.history[key])
            value = {
                **copy.deepcopy(self.preview_data),
                "id": 7,
                "client_request_id": key,
                "version": 1,
                "created_at": "2026-10-28T00:00:00Z",
                "deleted_at": None,
            }
            result = {"expense": value, "balances": None}
            self.saved[7] = value
            self.history[key] = copy.deepcopy(result)
            if self.fail_after == "POST":
                self.fail_after = None
                raise httpx.ReadTimeout("private transport diagnostic")
            return httpx.Response(201, json=result)
        eid = int(path.rsplit("/", 1)[1])
        existing = self.saved.get(eid)
        if existing is None or (existing["deleted_at"] and method != "DELETE"):
            return error(404, "expense_not_found")
        value = existing
        if method == "GET":
            return httpx.Response(200, json=value)
        if method == "PUT":
            if body["expected_version"] != value["version"]:
                return error(409, "expense_version_conflict")
            value = {
                **value,
                **copy.deepcopy(self.preview_data),
                "version": value["version"] + 1,
            }
            self.saved[eid] = value
        elif method == "DELETE":
            if not value["deleted_at"]:
                if int(request.url.params["expected_version"]) != value["version"]:
                    return error(409, "expense_version_conflict")
                value["deleted_at"], value["version"] = (
                    "2026-10-28T01:00:00Z",
                    value["version"] + 1,
                )
        else:
            raise AssertionError("Unexpected method")
        if self.fail_after == method:
            self.fail_after = None
            raise httpx.ReadTimeout("private transport diagnostic")
        return httpx.Response(200, json={"expense": value, "balances": None})


@dataclass
class ExpenseJourney:
    ui: Harness
    server: ExpenseServer

    def button(self, label: str) -> str:
        for sent in reversed(self.ui.sent):
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
                return values[0]
        raise AssertionError((label, self.ui.sent[-1].text))

    async def choose(self, label: str) -> str:
        value = self.button(label)
        await self.ui.click(value)
        return value

    @property
    def text(self) -> str:
        return "\n".join(m.text for m in self.ui.sent)

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [
            r for r in self.server.requests if (r.method, r.url.path) == (method, path)
        ]

    async def start(self, mode: str = "by_items") -> None:
        self.server.profile = self.server.user()
        self.server.groups = [self.server.group(100)]
        await self.ui.send("/start")
        await self.ui.click("menu:groups")
        await self.choose("Группа 100 · #100")
        await self.choose("Добавить расход")
        await self.choose(
            {
                "equal": "Поровну — equal",
                "custom": "Точные суммы — custom",
                "by_items": "По позициям — by_items",
            }[mode]
        )

    async def receipt(self) -> None:
        await self.start()
        await self.ui.send("Ресторан")
        for index, item in enumerate(O05["preview_request"]["items"]):
            if index:
                await self.choose("Добавить позицию")
            await self.ui.send(item["title"])
            await self.ui.send(item["amount"])
            for uid in item["participants"]:
                await self.choose(f"Участник #{uid}")
            await self.choose("Готово")

    async def simple(self, mode: str = "equal", amount: str = "100.00") -> None:
        self.server.preview_data = {
            **copy.deepcopy(O04["preview_response"]),
            "group_id": 100,
            "payer_id": 10,
            "split_mode": mode,
            "shares": [
                {"user_id": uid, "amount": value}
                for uid, value in zip(
                    [10, 20, 30], ["33.34", "33.33", "33.33"], strict=True
                )
            ],
        }
        await self.start(mode)
        await self.ui.send("Обед")
        await self.ui.send(amount)
        await self.choose("Выбрать всех")
        await self.choose("Готово")
        if mode == "custom":
            for value in ["0.00", "40.00", "60.00"]:
                await self.ui.send(value)
            self.server.preview_data["shares"] = [
                {"user_id": uid, "amount": value}
                for uid, value in zip(
                    [10, 20, 30], ["0.00", "40.00", "60.00"], strict=True
                )
            ]


@pytest.fixture
async def expense_journey() -> AsyncIterator[ExpenseJourney]:
    server = ExpenseServer()
    session = AsyncMock(spec=BaseSession)
    bot = Bot(
        token=f"{secrets.randbelow(10**8) + 1}:{secrets.token_urlsafe(32)}",
        session=session,
    )
    dispatcher = create_dispatcher()
    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(server.respond),
    ) as api:
        try:
            yield ExpenseJourney(Harness(bot, dispatcher, session, api, []), server)
        finally:
            await dispatcher.fsm.close()
            await bot.session.close()


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["equal", "custom", "by_items"])
async def test_create_modes_only_after_server_preview(
    expense_journey: ExpenseJourney, mode: str
) -> None:
    j = expense_journey
    await (j.receipt() if mode == "by_items" else j.simple(mode))
    assert not j.server.saved
    await j.choose("Серверный предпросмотр")
    assert not j.server.saved
    assert "Серверный предпросмотр — ещё не сохранено" in j.text
    confirm = await j.choose("Подтвердить расход")
    await j.ui.click(confirm)
    writes = j.calls("POST", "/internal/groups/100/expenses")
    assert len(writes) == 1 and len(j.server.saved) == 1
    body = json.loads(writes[0].content)
    if mode == "by_items":
        assert "amount" not in body and body["items"] == O05["preview_request"]["items"]
        for value in ["3200.00", "1000.00", "1400.00", "800.00"]:
            assert value in j.text
    elif mode == "custom":
        assert body["shares"][0] == {"user_id": 10, "amount": "0.00"}
    assert "Сохранённый расход #7" in j.text


@pytest.mark.anyio
async def test_post_timeout_replays_exact_intent_then_gets_current(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.receipt()
    await j.choose("Серверный предпросмотр")
    j.server.fail_after = "POST"
    await j.choose("Подтвердить расход")
    assert await j.ui.state.get_state() == ExpenseFlow.post_uncertain.state
    assert "подтвердил исходное создание" not in j.text
    # Original replay differs from current state; UI must explicitly GET current.
    j.server.saved[7]["title"] = "Позже исправлено"
    j.server.saved[7]["version"] = 2
    await j.choose("Повторить исходный запрос")
    writes = j.calls("POST", "/internal/groups/100/expenses")
    assert len(writes) == 2 and writes[0].content == writes[1].content
    assert len(j.server.saved) == 1 and "Позже исправлено" in j.text
    assert j.calls("GET", "/internal/expenses/7")


@pytest.mark.anyio
async def test_preview_edit_invalidation_and_new_intent_uuid(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    stale = j.button("Подтвердить расход")
    await j.choose("Исправить черновик")
    await j.choose("Изменить название")
    await j.ui.send("Другой обед")
    await j.ui.click(stale)
    assert not j.server.saved
    assert (await load(j.ui.state)).preview_body is None
    j.server.preview_data["title"] = "Другой обед"
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    first_key = j.server.saved[7]["client_request_id"]
    await j.choose("К расходам")
    await j.choose("Добавить расход")
    await j.choose("Поровну — equal")
    await j.ui.send("Ещё")
    await j.ui.send("100.00")
    await j.choose("Выбрать всех")
    await j.choose("Готово")
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    assert j.server.saved[7]["client_request_id"] != first_key


@pytest.mark.anyio
async def test_custom_server_validation_preserves_zero_and_all_fields(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple("custom")
    j.server.overrides["POST", "/internal/groups/100/expenses/preview"] = [
        error(400, "validation_error")
    ]
    await j.choose("Серверный предпросмотр")
    draft = await load(j.ui.state)
    assert draft.shares == {"10": "0.00", "20": "40.00", "30": "60.00"}
    assert draft.preview_body is None and not j.server.saved
    assert "точное совпадение custom-долей" in j.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        "0.00",
        "-1.00",
        "1,00",
        "1.001",
        "1e2",
        "01.00",
        " 1.00",
        "١.٠٠",
        "NaN",
        "10000000.00",
    ],
)
async def test_bad_money_stays_at_input(
    expense_journey: ExpenseJourney, bad: str
) -> None:
    j = expense_journey
    await j.start("equal")
    await j.ui.send("Обед")
    await j.ui.send(bad)
    assert await j.ui.state.get_state() == ExpenseFlow.amount.state
    assert not j.server.saved


@pytest.mark.anyio
async def test_empty_selection_toggle_and_mode_switch(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple("custom")
    await j.choose("Выбрать участников")
    await j.choose("✓ Участник #10")
    await j.choose("✓ Участник #20")
    await j.choose("✓ Участник #30")
    await j.choose("Готово")
    assert "Выберите хотя бы одного" in j.text
    await j.choose("Участник #20")
    await j.choose("✓ Участник #20")
    await j.choose("Участник #20")
    await j.choose("Готово")
    await j.ui.send("100.00")
    draft = await load(j.ui.state)
    assert draft.selected == [20] and draft.shares == {"20": "100.00"}
    await j.choose("Сменить режим")
    await j.choose("По позициям — by_items")
    draft = await load(j.ui.state)
    assert not draft.amount and not draft.selected and not draft.shares
    await j.choose("Серверный предпросмотр")
    assert not j.calls("POST", "/internal/groups/100/expenses/preview")
    assert "1–50" in j.text


@pytest.mark.anyio
async def test_long_receipt_edit_drop_and_50_limit(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.start()
    draft = await load(j.ui.state)
    draft.title = "Длинный чек"
    from bot.expense_dto import ReceiptItem

    draft.items = [
        ReceiptItem(title="Я" * 120, amount="0.01", participants=[10, 20, 30])
        for _ in range(50)
    ]
    await keep(j.ui.state, draft)
    from bot.expense_wizard import review

    await review(j.ui.message("").as_(j.ui.bot), j.ui.state, draft)
    assert all(len(m.text) <= 4096 for m in j.ui.sent)
    markup = str(j.ui.sent[-1].reply_markup)
    assert "Добавить позицию" not in markup
    await j.choose("Изменить/убрать позицию")
    await j.choose("1. " + "Я" * 35)
    await j.choose("Убрать позицию")
    assert len((await load(j.ui.state)).items) == 49
    await j.choose("Добавить позицию")
    await j.ui.send("Новая")
    await j.ui.send("1.00")
    await j.choose("Участник #10")
    await j.choose("Готово")
    draft = await load(j.ui.state)
    assert len(draft.items) == 50 and draft.items[-1].title == "Новая"


@pytest.mark.anyio
async def test_list_pagination_detail_owner_is_not_author(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.receipt()
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    original = j.server.saved[7]
    j.server.saved = {
        i: {**copy.deepcopy(original), "id": i, "payer_id": 20} for i in range(1, 22)
    }
    await j.choose("К расходам")
    await j.choose("Далее")
    assert dict(j.calls("GET", "/internal/groups/100/expenses")[-1].url.params) == {
        "limit": "20",
        "offset": "20",
    }
    await j.choose("Открыть #21 · Ресторан")
    assert "Редактировать" not in str(j.ui.sent[-1].reply_markup)
    assert "Удалить" not in str(j.ui.sent[-1].reply_markup)
    assert "Плательщик: участник #20" in j.text
    await j.choose("К расходам")
    j.server.saved.clear()
    await j.choose("Обновить")
    assert "расходов нет" in j.ui.sent[-1].text


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["PUT", "DELETE"])
@pytest.mark.parametrize("outcome", ["success", "timeout", "stale"])
async def test_edit_delete_versions_and_recovery(
    expense_journey: ExpenseJourney, mutation: str, outcome: str
) -> None:
    j = expense_journey
    await j.receipt()
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    await j.choose("Редактировать" if mutation == "PUT" else "Удалить")
    assert "обратного долга" in j.ui.sent[-1].text
    if mutation == "PUT":
        await j.choose("Продолжить редактирование")
        await j.choose("Сменить режим")
        await j.choose("Точные суммы — custom")
        await j.choose("Изменить сумму")
        await j.ui.send("1.00")
        await j.choose("Участник #20")
        await j.choose("Готово")
        await j.ui.send("1.00")
        j.server.preview_data = {
            "group_id": 100,
            "payer_id": 10,
            "title": "Ресторан",
            "split_mode": "custom",
            "amount": "1.00",
            "shares": [{"user_id": 20, "amount": "1.00"}],
        }
        await j.choose("Серверный предпросмотр")
    if outcome == "timeout":
        j.server.fail_after = mutation
    if outcome == "stale":
        j.server.saved[7]["version"] = 5
    await j.choose("Сохранить изменения" if mutation == "PUT" else "Да, удалить расход")
    calls = j.calls(mutation, "/internal/expenses/7")
    assert len(calls) == 1
    if mutation == "PUT":
        assert json.loads(calls[0].content)["expected_version"] == 1
        assert "items" not in json.loads(calls[0].content)
        if outcome != "success":
            assert j.calls("GET", "/internal/expenses/7")
        if outcome == "stale":
            assert j.server.saved[7]["version"] == 5
        else:
            assert j.server.saved[7]["version"] == 2
    else:
        assert calls[0].url.params["expected_version"] == "1"
        if outcome == "timeout":
            await j.choose("Повторить удаление")
            calls = j.calls(mutation, "/internal/expenses/7")
            assert len(calls) == 2 and calls[0].url == calls[1].url
        if outcome != "stale":
            assert j.server.saved[7]["version"] == 2 and j.server.saved[7]["deleted_at"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "step",
    [
        "mode",
        "title",
        "amount",
        "participants",
        "share",
        "item_title",
        "item_amount",
        "preview",
    ],
)
async def test_cancel_start_restart_no_financial_write(
    expense_journey: ExpenseJourney, step: str
) -> None:
    j = expense_journey
    await j.simple()
    if step == "preview":
        await j.choose("Серверный предпросмотр")
    await j.ui.state.set_state(getattr(ExpenseFlow, step))
    old = j.ui.sent[-1].reply_markup
    before = await j.ui.state.get_data()
    await j.ui.send("/start")
    assert before == await j.ui.state.get_data()
    await j.ui.send("/help")
    await j.ui.send("/cancel")
    assert "expense_session" not in await j.ui.state.get_data()
    assert not j.server.saved
    assert old is not None
    await j.ui.click("l3:missing:0")
    assert "черновик потерян" in j.ui.sent[-1].text


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500, 503, 429])
async def test_safe_errors_no_false_success_or_secret_leak(
    expense_journey: ExpenseJourney, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    secret = secrets.token_urlsafe(48)
    j.server.overrides["POST", "/internal/groups/100/expenses"] = [
        httpx.Response(
            status,
            json={
                "error": {"code": "unknown", "message": secret, "request_id": secret}
            },
        )
    ]
    with caplog.at_level(logging.DEBUG):
        confirm = await j.choose("Подтвердить расход")
        await j.ui.click(confirm)
    assert secret not in j.text + caplog.text
    assert "подтвердил исходное создание" not in j.text
    assert not j.server.saved
    assert len(j.calls("POST", "/internal/groups/100/expenses")) == 1


@pytest.mark.anyio
async def test_exact_duplicate_telegram_update_and_foreign_callback(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    button = j.button("Подтвердить расход")
    await j.ui.click(button, user_id=456)
    assert not j.server.saved
    await j.ui.send("да")
    assert not j.server.saved
    await j.choose("Подтвердить расход")
    update_id = j.ui.update_id
    await j.ui.dispatcher.feed_update(
        j.ui.bot,
        Update(update_id=update_id, message=j.ui.message("/cancel")),
        api=j.ui.api,
    )
    assert len(j.calls("POST", "/internal/groups/100/expenses")) == 1


def test_wire_fixtures_and_shape_constraints_no_money_algorithms() -> None:
    for fixture in [O04, O05]:
        body = DRAFT.validate_python(fixture["preview_request"])
        assert body.model_dump(mode="json") == fixture["preview_request"]
        PREVIEW.validate_python(fixture["preview_response"])
        ExpenseMutation.model_validate_json(json.dumps(fixture["create_response"]))
        EXPENSE.validate_json(
            json.dumps(fixture.get("detail_response", fixture.get("equal_read")))
        )
    for path in (ROOT / "bot").glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        assert not any(
            isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app")
            for n in ast.walk(tree)
        )
        assert (
            not any(
                isinstance(n, ast.Constant) and isinstance(n.value, float)
                for n in ast.walk(tree)
            )
            or path.name == "api_client.py"
        )
        assert not any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in {"float", "round", "sum", "divmod"}
            for n in ast.walk(tree)
        )


@pytest.mark.parametrize(
    "change",
    ["empty", "duplicate", "too_many", "root_amount", "actor", "item_position"],
)
def test_invalid_receipt_shapes(change: str) -> None:
    body = copy.deepcopy(O05["preview_request"])
    if change == "empty":
        body["items"] = []
    elif change == "duplicate":
        body["items"][0]["participants"] = [10, 10]
    elif change == "too_many":
        body["items"] = [body["items"][0]] * 51
    elif change == "root_amount":
        body["amount"] = "3200.00"
    elif change == "actor":
        body["payer_id"] = 10
    else:
        body["items"][0]["position"] = 1
    with pytest.raises(ValidationError):
        DRAFT.validate_python(body)


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["POST", "DELETE"])
async def test_reading_list_does_not_lose_unknown_write_intent(
    expense_journey: ExpenseJourney, mutation: str
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    if mutation == "POST":
        j.server.fail_after = "POST"
        await j.choose("Подтвердить расход")
        frozen = (await load(j.ui.state)).sent_body
    else:
        await j.choose("Подтвердить расход")
        await j.choose("Удалить")
        j.server.fail_after = "DELETE"
        await j.choose("Да, удалить расход")
        frozen = ""
    await j.choose("Проверить расходы")
    assert "Добавить расход" not in str(j.ui.sent[-1].reply_markup)
    if mutation == "POST":
        assert (await load(j.ui.state)).sent_body == frozen
        await j.choose("Открыть #7 · Обед")
        assert "Редактировать" not in str(j.ui.sent[-1].reply_markup)
    await j.choose("К восстановлению запроса")
    await j.choose(
        "Повторить исходный запрос" if mutation == "POST" else "Повторить удаление"
    )
    assert j.server.saved[7]["version"] == (1 if mutation == "POST" else 2)


@pytest.mark.anyio
async def test_put_timeout_failed_read_rechecks_without_second_put(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    await j.choose("Редактировать")
    await j.choose("Продолжить редактирование")
    await j.choose("Серверный предпросмотр")
    j.server.fail_after = "PUT"
    j.server.overrides["GET", "/internal/expenses/7"] = [
        httpx.ConnectError("private read diagnostic")
    ]
    await j.choose("Сохранить изменения")
    assert await j.ui.state.get_state() == ExpenseFlow.put_uncertain.state
    assert "API подтвердил сохранение изменений" not in j.text
    await j.choose("Перечитать актуальную версию")
    assert len(j.calls("PUT", "/internal/expenses/7")) == 1
    assert "версия 2" in j.text


@pytest.mark.anyio
async def test_penny_three_consumers_preserves_explicit_zero_rows(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.start()
    await j.ui.send("Копейка")
    await j.ui.send("Чай")
    await j.ui.send("0.01")
    await j.choose("Выбрать всех")
    await j.choose("Готово")
    j.server.preview_data = {
        **copy.deepcopy(O05["penny_preview"]),
        "title": "Копейка",
        "amount": "0.01",
        "items": [copy.deepcopy(O05["penny_preview"]["items"][0])],
        "shares": [
            {"user_id": 10, "amount": "0.01"},
            {"user_id": 20, "amount": "0.00"},
            {"user_id": 30, "amount": "0.00"},
        ],
    }
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    value = j.server.saved[7]
    assert [s["amount"] for s in value["shares"]] == ["0.01", "0.00", "0.00"]
    assert "#20: 0.00 ₽" in j.text and "#30: 0.00 ₽" in j.text


@pytest.mark.anyio
async def test_edit_position_updates_in_place_without_reordering(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.receipt()
    await j.choose("Изменить/убрать позицию")
    await j.choose("2. Стейк")
    await j.ui.send("Новый стейк")
    await j.ui.send("1200.00")
    await j.choose("Готово")
    draft = await load(j.ui.state)
    assert [i.title for i in draft.items] == ["Паста", "Новый стейк", "Салат", "Пицца"]
    assert draft.items[1].participants == [20]
    assert draft.preview_body is None


@pytest.mark.anyio
async def test_stale_preview_body_is_refused_even_with_current_button(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    draft = await load(j.ui.state)
    draft.title = "Изменённый ввод"
    # Simulate a changed draft behind an old preview without relying on nonce alone.
    await j.ui.state.update_data(expense_session=draft.model_dump_json())
    await j.choose("Подтвердить расход")
    assert not j.server.saved and "Предпросмотр устарел" in j.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code",
    [
        "invalid_participants",
        "expense_author_required",
        "request_conflict",
        "request_history_unavailable",
    ],
)
async def test_expense_error_codes_do_not_invent_details(
    expense_journey: ExpenseJourney, code: str
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    j.server.overrides["POST", "/internal/groups/100/expenses"] = [
        error(
            400
            if code == "invalid_participants"
            else 403
            if code == "expense_author_required"
            else 409,
            code,
        )
    ]
    await j.choose("Подтвердить расход")
    assert not j.server.saved
    assert "подтвердил исходное создание" not in j.text
    assert len(j.calls("POST", "/internal/groups/100/expenses")) == 1


@pytest.mark.parametrize(
    "mode,selection",
    [("equal", []), ("equal", [10, 10]), ("custom", []), ("custom", [10, 10])],
)
def test_empty_duplicate_equal_custom_rejected_as_shape(
    mode: str, selection: list[int]
) -> None:
    body = {"title": "Обед", "amount": "1.00", "split_mode": mode}
    extra = (
        {"participants": selection}
        if mode == "equal"
        else {"shares": [{"user_id": uid, "amount": "0.00"} for uid in selection]}
    )
    with pytest.raises(ValidationError):
        DRAFT.validate_python(body | extra)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad", ["", " " * 10, "я" * 121, "Невидимый\u200d", "Строка\nЧек"]
)
async def test_invalid_title_not_echoed_or_advanced(
    expense_journey: ExpenseJourney, bad: str
) -> None:
    j = expense_journey
    await j.start("equal")
    await j.ui.send(bad)
    assert await j.ui.state.get_state() == ExpenseFlow.title.state
    assert not (await load(j.ui.state)).title
