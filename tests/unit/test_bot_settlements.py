"""L-05 real Dispatcher + client. HTTP and Telegram transports both mocked."""

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
from pydantic import SecretStr

from bot.api_client import ApiClient
from bot.main import create_dispatcher
from bot.settlement_state import load
from bot.states import SettlementFlow
from tests.unit.test_bot_handlers import Harness
from tests.unit.test_bot_onboarding_groups import ContractFixture, error

ROOT = Path(__file__).resolve().parents[2]
O06 = json.loads((ROOT / "docs/finance/fixtures/O-06_BALANCES.json").read_text("utf-8"))
O07 = json.loads(
    (ROOT / "docs/finance/fixtures/O-07_SETTLEMENTS.json").read_text("utf-8")
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class SettlementServer(ContractFixture):
    owner: int = 20
    saved: dict[int, dict[str, Any]] = field(default_factory=dict)
    history: dict[str, dict[str, Any]] = field(default_factory=dict)
    balances_data: dict[str, Any] = field(
        default_factory=lambda: copy.deepcopy(O06["balances"])
    )
    plan_data: dict[str, Any] = field(
        default_factory=lambda: copy.deepcopy(O06["plan"])
    )
    fail_after: str | None = None

    def group(self, group_id: int = 10) -> dict[str, object]:
        return {
            "id": group_id,
            "name": f"Группа {group_id}",
            "owner_id": 10,
            "created_at": "2026-10-30T00:00:00Z",
        }

    def record(self, status: str = "pending", *, sid: int = 123) -> dict[str, Any]:
        return {
            **copy.deepcopy(O07["create"]["settlement"]),
            "id": sid,
            "status": status,
            "resolved_at": None if status == "pending" else "2026-10-30T12:01:00Z",
        }

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if not (
            path.startswith("/internal/groups/10")
            or path.startswith("/internal/settlements/")
        ):
            return super().respond(request)
        self.requests.append(request)
        assert request.headers["X-Telegram-ID"] == "123"
        assert (
            request.headers["X-Bot-Service-Token"]
            and "authorization" not in request.headers
        )
        if self.overrides.get((method, path)):
            override = self.overrides[method, path].pop(0)
            if isinstance(override, Exception):
                raise override
            return override
        if path == "/internal/groups/10":
            return httpx.Response(200, json=self.group())
        if path.endswith("/members"):
            offset = int(request.url.params["offset"])
            items = [
                {
                    "user_id": uid,
                    "is_owner": uid == 10,
                    "joined_at": "2026-10-30T00:00:00Z",
                }
                for uid in [10, 20, 30, 40]
            ]
            return httpx.Response(
                200,
                json={
                    "items": items[offset : offset + 20],
                    "limit": 20,
                    "offset": offset,
                },
            )
        if path.endswith("/balances"):
            return httpx.Response(200, json=self.balances_data)
        if path.endswith("/settlement-plan"):
            return httpx.Response(200, json=self.plan_data)
        body = json.loads(request.content) if request.content else {}
        if path == "/internal/groups/10/settlements":
            if method == "GET":
                status = request.url.params.get("status")
                direction = request.url.params["direction"]
                offset = int(request.url.params["offset"])
                assert request.url.params["limit"] == "20"
                values = [
                    s
                    for s in self.saved.values()
                    if (not status or s["status"] == status)
                    and (
                        direction == "all"
                        or (
                            s["receiver_id"]
                            if direction == "incoming"
                            else s["sender_id"]
                        )
                        == self.owner
                    )
                ]
                return httpx.Response(
                    200,
                    json={
                        "items": values[offset : offset + 20],
                        "limit": 20,
                        "offset": offset,
                    },
                )
            assert set(body) == {"receiver_id", "amount", "client_request_id"}
            key = body["client_request_id"]
            if key in self.history:
                return httpx.Response(200, json=self.history[key])
            sid = 123 + len(self.saved)
            record = {
                **self.record(sid=sid),
                "sender_id": self.owner,
                "receiver_id": body["receiver_id"],
                "amount": body["amount"],
                "client_request_id": key,
            }
            result = {"settlement": record}
            self.saved[sid] = record
            self.history[key] = copy.deepcopy(result)
            if self.fail_after == "create":
                self.fail_after = None
                raise httpx.ReadTimeout("private dropped response")
            return httpx.Response(201, json=result)
        _, _, _, sid_text, operation = path.split("/")
        existing = self.saved.get(int(sid_text))
        if existing is None:
            return error(404, "settlement_not_found")
        record = existing
        assert body == {}
        if (
            record["sender_id"] if operation == "cancel" else record["receiver_id"]
        ) != self.owner:
            return error(
                403,
                "settlement_sender_required"
                if operation == "cancel"
                else "settlement_receiver_required",
            )
        target = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}[
            operation
        ]
        if record["status"] not in {"pending", target}:
            return error(409, "settlement_state_conflict")
        record["status"], record["resolved_at"] = target, "2026-10-30T12:01:00Z"
        if target == "confirmed":
            # Canned server results, not a client-side calculator.
            self.balances_data = {
                "group_id": 10,
                "balances": [
                    {"user_id": 10, "balance": "1700.00"},
                    {"user_id": 20, "balance": "-900.00"},
                    {"user_id": 30, "balance": "-800.00"},
                ],
            }
            self.plan_data = {
                "group_id": 10,
                "transfers": [
                    {"sender_id": 20, "receiver_id": 10, "amount": "900.00"},
                    {"sender_id": 30, "receiver_id": 10, "amount": "800.00"},
                ],
            }
        if self.fail_after == operation:
            self.fail_after = None
            raise httpx.ReadTimeout("private dropped transition response")
        return httpx.Response(200, json={"settlement": record})


@dataclass
class SettlementJourney:
    ui: Harness
    server: SettlementServer

    def button(self, label: str) -> str:
        for sent in reversed(self.ui.sent):
            markup = sent.reply_markup
            if isinstance(markup, InlineKeyboardMarkup):
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
        button = self.button(label)
        await self.ui.click(button)
        return button

    @property
    def text(self) -> str:
        return "\n".join(m.text for m in self.ui.sent)

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [
            r for r in self.server.requests if (r.method, r.url.path) == (method, path)
        ]

    async def group(self) -> None:
        self.server.profile = self.server.user()
        self.server.groups = [self.server.group()]
        await self.ui.send("/start")
        await self.ui.click("menu:groups")
        await self.choose("Группа 10 · #10")

    async def draft(self, amount: str = "500.00") -> None:
        await self.group()
        await self.choose("Я перевёл деньги")
        await self.choose("Участник #10")
        await self.ui.send(amount)

    async def open(self, status: str = "pending") -> None:
        self.server.saved[123] = self.server.record(status)
        await self.group()
        await self.choose("История переводов")
        await self.choose("Открыть перевод #123")


@pytest.fixture
async def settlement_journey() -> AsyncIterator[SettlementJourney]:
    server = SettlementServer()
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
            yield SettlementJourney(Harness(bot, dispatcher, session, api, []), server)
        finally:
            await dispatcher.fsm.close()
            await bot.session.close()


@pytest.mark.anyio
async def test_balances_plan_are_exact_read_only_and_refresh(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    j.server.balances_data["balances"].append({"user_id": 40, "balance": "0.00"})
    await j.group()
    await j.choose("Балансы")
    assert "2200.00 ₽ — участнику должны" in j.text
    assert "-1400.00 ₽ — участник должен" in j.text
    assert "0.00 ₽ — долгов нет" in j.text
    await j.choose("Обновить балансы")
    assert len(j.calls("GET", "/internal/groups/10/balances")) == 2
    await j.choose("План переводов")
    assert "#20 → Участник #10: 1400.00 ₽" in j.text
    assert "Минимальное число переводов не обещается" in j.text
    j.server.plan_data["transfers"] = []
    await j.choose("Обновить план")
    assert "По текущему плану переводов нет" in j.text
    assert not j.server.saved and all(r.method == "GET" for r in j.server.requests)


@pytest.mark.anyio
@pytest.mark.parametrize("amount", ["500.00", "1000001.00", "92233720368547758.07"])
async def test_pending_partial_and_no_expense_cap(
    settlement_journey: SettlementJourney, amount: str
) -> None:
    j = settlement_journey
    await j.draft(amount)
    assert not j.server.saved and "уже отправили" in j.text
    before = copy.deepcopy(j.server.balances_data)
    old = await j.choose("Да, я уже перевёл деньги")
    await j.ui.click(old)
    assert len(j.server.saved) == 1 and j.server.saved[123]["status"] == "pending"
    assert j.server.balances_data == before
    calls = j.calls("POST", "/internal/groups/10/settlements")
    assert len(calls) == 1 and json.loads(calls[0].content)["amount"] == amount
    assert "Актуальный статус API: pending" in j.text
    assert (
        j.calls("GET", "/internal/groups/10/settlements")[-1].url.params["direction"]
        == "outgoing"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "operation,owner", [("confirm", 10), ("reject", 10), ("cancel", 20)]
)
async def test_role_transition_with_warning_and_current_server_response(
    settlement_journey: SettlementJourney, operation: str, owner: int
) -> None:
    j = settlement_journey
    j.server.owner = owner
    await j.open()
    label = {
        "confirm": "Подтвердить получение",
        "reject": "Отклонить",
        "cancel": "Отменить заявку",
    }[operation]
    await j.choose(label)
    assert "реально полученные деньги" in j.ui.sent[-1].text
    confirm = {
        "confirm": "Да, деньги получены",
        "reject": "Да, отклонить",
        "cancel": "Да, отменить заявку",
    }[operation]
    stale = await j.choose(confirm)
    await j.ui.click(stale)
    assert len(j.calls("POST", f"/internal/settlements/123/{operation}")) == 1
    target = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}[
        operation
    ]
    assert j.server.saved[123]["status"] == target
    assert f"Актуальный статус API: {target}" in j.text
    assert label not in str(j.ui.sent[-2].reply_markup)
    if operation == "confirm":
        assert j.calls("GET", "/internal/groups/10/balances") and j.calls(
            "GET", "/internal/groups/10/settlement-plan"
        )
        assert "1700.00" in j.text and "-900.00" in j.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "owner,hidden",
    [(20, "Подтвердить получение"), (10, "Отменить заявку"), (30, "Отклонить")],
)
async def test_wrong_roles_hidden_even_for_group_owner(
    settlement_journey: SettlementJourney, owner: int, hidden: str
) -> None:
    j = settlement_journey
    j.server.owner = owner
    await j.open()
    assert hidden not in str(j.ui.sent[-1].reply_markup)
    assert all(r.method == "GET" for r in j.server.requests)


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["confirmed", "rejected", "cancelled"])
async def test_terminal_records_have_no_mutation_buttons(
    settlement_journey: SettlementJourney, status: str
) -> None:
    j = settlement_journey
    await j.open(status)
    markup = str(j.ui.sent[-1].reply_markup)
    assert all(
        label not in markup
        for label in ["Подтвердить получение", "Отклонить", "Отменить заявку"]
    )
    assert all(r.method == "GET" for r in j.server.requests)


@pytest.mark.anyio
async def test_lost_create_response_then_terminal_original_replay_reads_current(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    await j.draft()
    j.server.fail_after = "create"
    await j.choose("Да, я уже перевёл деньги")
    assert "API подтвердил исходное создание" not in j.text
    frozen = (await load(j.ui.state)).frozen
    j.server.saved[123]["status"] = "confirmed"
    j.server.saved[123]["resolved_at"] = "2026-10-30T12:01:00Z"
    await j.choose("История переводов")
    assert (await load(j.ui.state)).frozen == frozen
    assert "Я перевёл деньги" not in str(j.ui.sent[-1].reply_markup)
    await j.choose("К восстановлению заявки")
    await j.choose("Повторить исходную заявку")
    posts = j.calls("POST", "/internal/groups/10/settlements")
    assert len(posts) == 2 and posts[0].content == posts[1].content
    assert (
        j.server.history[next(iter(j.server.history))]["settlement"]["status"]
        == "pending"
    )
    assert "Актуальный статус API: confirmed" in j.text
    assert "Актуальный статус API: pending" not in j.text
    assert len(j.server.saved) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "operation,owner", [("confirm", 10), ("reject", 10), ("cancel", 20)]
)
async def test_transition_lost_response_uses_list_not_fake_success(
    settlement_journey: SettlementJourney, operation: str, owner: int
) -> None:
    j = settlement_journey
    j.server.owner = owner
    await j.open()
    await j.choose(
        {
            "confirm": "Подтвердить получение",
            "reject": "Отклонить",
            "cancel": "Отменить заявку",
        }[operation]
    )
    j.server.fail_after = operation
    await j.choose(
        {
            "confirm": "Да, деньги получены",
            "reject": "Да, отклонить",
            "cancel": "Да, отменить заявку",
        }[operation]
    )
    assert "Результат пока неизвестен" in j.text
    assert "API подтвердил статус" not in j.text
    target = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}[
        operation
    ]
    assert f"Актуальный статус API: {target}" in j.text
    assert len(j.calls("POST", f"/internal/settlements/123/{operation}")) == 1


@pytest.mark.anyio
async def test_timeout_before_confirm_keeps_pending_and_explicit_same_retry(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    j.server.owner = 10
    await j.open()
    await j.choose("Подтвердить получение")
    j.server.overrides["POST", "/internal/settlements/123/confirm"] = [
        httpx.ReadTimeout("private")
    ]
    await j.choose("Да, деньги получены")
    assert await j.ui.state.get_state() == SettlementFlow.transition_unknown.state
    assert "API подтвердил статус" not in j.text
    assert j.server.saved[123]["status"] == "pending"
    assert "Отклонить" not in str(j.ui.sent[-1].reply_markup)
    await j.choose("Повторить то же действие")
    assert j.server.saved[123]["status"] == "confirmed"
    assert len(j.calls("POST", "/internal/settlements/123/confirm")) == 2


@pytest.mark.anyio
async def test_balance_conflict_does_not_rewrite_pending_or_amount(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    j.server.owner = 10
    await j.open()
    await j.choose("Подтвердить получение")
    j.server.overrides["POST", "/internal/settlements/123/confirm"] = [
        error(409, "settlement_balance_conflict")
    ]
    await j.choose("Да, деньги получены")
    assert (
        j.server.saved[123]["status"] == "pending"
        and j.server.saved[123]["amount"] == "500.00"
    )
    assert "Долг или доступный кредит изменился" in j.text
    assert "Отклонить" in str(j.ui.sent[-1].reply_markup)


@pytest.mark.anyio
async def test_filters_pagination_empty_and_current_record_search(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    j.server.saved = {
        i: {
            **j.server.record(sid=i),
            "status": "confirmed",
            "resolved_at": "2026-10-30T12:01:00Z",
        }
        for i in range(1, 22)
    }
    await j.group()
    await j.choose("История переводов")
    await j.choose("Статус: confirmed")
    await j.choose("Направление: исходящие")
    await j.choose("Далее")
    assert dict(j.calls("GET", "/internal/groups/10/settlements")[-1].url.params) == {
        "limit": "20",
        "offset": "20",
        "direction": "outgoing",
        "status": "confirmed",
    }
    await j.choose("Открыть перевод #21")
    assert "На проверенной странице запись не найдена" in j.ui.sent[-1].text
    await j.choose("Следующая страница поиска")
    assert "Актуальный статус API: confirmed" in j.text
    await j.choose("Ожидают подтверждения")
    assert "На этой странице переводов нет" in j.ui.sent[-1].text
    assert dict(j.calls("GET", "/internal/groups/10/settlements")[-1].url.params) == {
        "limit": "20",
        "offset": "0",
        "direction": "incoming",
        "status": "pending",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        "0.00",
        "-1.00",
        "+1.00",
        "1,00",
        "1.0",
        "1.001",
        "1e2",
        "01.00",
        " 1.00",
        "١.٠٠",
        "9" * 21,
    ],
)
async def test_bad_amount_stays_at_input(
    settlement_journey: SettlementJourney, bad: str
) -> None:
    j = settlement_journey
    await j.group()
    await j.choose("Я перевёл деньги")
    await j.choose("Участник #10")
    await j.ui.send(bad)
    assert (
        await j.ui.state.get_state() == SettlementFlow.amount.state
        and not j.server.saved
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "step",
    [
        "receiver",
        "amount",
        "review",
        "search",
        "create_unknown",
        "transition_confirm",
        "transition_unknown",
    ],
)
async def test_start_help_cancel_restart_and_stale_callbacks(
    settlement_journey: SettlementJourney, step: str
) -> None:
    j = settlement_journey
    await j.draft()
    stale = j.button("Да, я уже перевёл деньги")
    await j.ui.state.set_state(getattr(SettlementFlow, step))
    before = await j.ui.state.get_data()
    await j.ui.send("/start")
    await j.ui.send("/help")
    assert await j.ui.state.get_data() == before
    await j.ui.send("/cancel")
    assert (
        not j.server.saved and "settlement_session" not in await j.ui.state.get_data()
    )
    await j.ui.click(stale)
    assert "черновик потерян" in j.ui.sent[-1].text


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 429, 500, 503])
async def test_safe_errors_no_success_or_leaks(
    settlement_journey: SettlementJourney, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    j = settlement_journey
    await j.draft()
    secret = secrets.token_urlsafe(48)
    j.server.overrides["POST", "/internal/groups/10/settlements"] = [
        httpx.Response(
            status,
            json={
                "error": {"code": "unknown", "message": secret, "request_id": secret}
            },
        )
    ]
    with caplog.at_level(logging.DEBUG):
        button = await j.choose("Да, я уже перевёл деньги")
        await j.ui.click(button)
    assert secret not in j.text + caplog.text and not j.server.saved
    assert "API подтвердил исходное создание" not in j.text
    assert len(j.calls("POST", "/internal/groups/10/settlements")) == 1


@pytest.mark.anyio
async def test_main_pending_menu_dedup_and_foreign_callback(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    await j.group()
    await j.ui.click("menu:pending")
    await j.choose("Группа 10 · #10")
    assert (
        j.calls("GET", "/internal/groups/10/settlements")[-1].url.params["direction"]
        == "incoming"
    )
    await j.choose("Я перевёл деньги")
    assert "Участник #20" not in str(j.ui.sent[-1].reply_markup)
    await j.choose("Участник #10")
    await j.ui.send("500.00")
    button = j.button("Да, я уже перевёл деньги")
    await j.ui.click(button, user_id=456)
    assert not j.server.saved
    await j.choose("Да, я уже перевёл деньги")
    await j.ui.dispatcher.feed_update(
        j.ui.bot,
        Update(update_id=j.ui.update_id, message=j.ui.message("/cancel")),
        api=j.ui.api,
    )
    assert len(j.calls("POST", "/internal/groups/10/settlements")) == 1


@pytest.mark.anyio
async def test_creation_ack_with_failed_read_has_no_fake_current_pending(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    await j.draft()
    j.server.overrides["GET", "/internal/groups/10/settlements"] = [
        error(503, "internal_error")
    ]
    await j.choose("Да, я уже перевёл деньги")
    assert "Актуальный статус API: pending" not in j.text
    assert (await load(j.ui.state)).frozen
    await j.choose("Повторить чтение статуса")
    assert "Актуальный статус API: pending" in j.text
    assert len(j.calls("POST", "/internal/groups/10/settlements")) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "screen_name", ["Балансы", "План переводов", "История переводов"]
)
async def test_wrong_group_success_payload_not_disclosed(
    settlement_journey: SettlementJourney, screen_name: str
) -> None:
    j = settlement_journey
    await j.group()
    if screen_name == "Балансы":
        j.server.balances_data = {
            "group_id": 999,
            "balances": [{"user_id": 999, "balance": "9876.54"}],
        }
    elif screen_name == "План переводов":
        j.server.plan_data = {
            "group_id": 999,
            "transfers": [{"sender_id": 999, "receiver_id": 10, "amount": "9876.54"}],
        }
    else:
        j.server.saved[123] = {
            **j.server.record(),
            "group_id": 999,
            "amount": "9876.54",
        }
    await j.choose(screen_name)
    assert "9876.54" not in j.text and "#999" not in j.text


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500, 503])
async def test_read_failures_offer_safe_repeat(
    settlement_journey: SettlementJourney, status: int
) -> None:
    j = settlement_journey
    await j.group()
    j.server.overrides["GET", "/internal/groups/10/balances"] = [
        error(status, "unknown")
    ]
    await j.choose("Балансы")
    assert "Балансы группы #10 (API)" not in j.text
    await j.choose("Обновить балансы")
    assert "2200.00" in j.text
