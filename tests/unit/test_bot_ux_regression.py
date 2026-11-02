"""L-06 failures preserve user intent and require fresh explicit actions."""

import copy
import json
import logging
import secrets
from uuid import uuid4

import httpx
import pytest

from bot.expense_wizard import load
from bot.settlement_notifications import NOTICE
from bot.states import ExpenseFlow
from tests.unit.test_bot_expenses import ExpenseJourney
from tests.unit.test_bot_expenses import expense_journey as expense_journey
from tests.unit.test_bot_settlements import SettlementJourney
from tests.unit.test_bot_settlements import settlement_journey as settlement_journey

pytestmark = pytest.mark.anyio
CREATE = "/internal/groups/100/expenses"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_known_rejected_save_preserves_draft_and_requires_new_preview(
    expense_journey: ExpenseJourney, status: int
) -> None:
    j = expense_journey
    await j.simple("custom")
    before = (await load(j.ui.state)).business()
    await j.choose("Серверный предпросмотр")
    j.server.overrides["POST", CREATE] = [httpx.Response(status)]
    old = await j.choose("Подтвердить расход")
    assert (await load(j.ui.state)).business() == before
    assert await j.ui.state.get_state() == ExpenseFlow.draft.state
    assert (await load(j.ui.state)).preview_body is None
    assert len(j.calls("POST", CREATE)) == 1 and not j.server.saved
    await j.ui.click(old)
    assert len(j.calls("POST", CREATE)) == 1
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    assert len(j.server.saved) == 1
    writes = j.calls("POST", CREATE)
    assert writes[0].content == writes[1].content


async def test_changed_rejected_draft_is_a_new_intent(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    j.server.overrides["POST", CREATE] = [httpx.Response(401)]
    await j.choose("Подтвердить расход")
    await j.choose("Изменить название")
    await j.ui.send("Другой обед")
    await j.choose("Серверный предпросмотр")
    await j.choose("Подтвердить расход")
    bodies = [json.loads(r.content) for r in j.calls("POST", CREATE)]
    assert bodies[0]["client_request_id"] != bodies[1]["client_request_id"]


@pytest.mark.parametrize("index", ["²", "Ⅻ", "-1", "999"])
async def test_malformed_callback_index_is_rejected_without_losing_current_screen(
    expense_journey: ExpenseJourney,
    index: str,
) -> None:
    j = expense_journey
    await j.simple()
    before = await j.ui.state.get_data()
    await j.ui.click(f"l3:{before['screen']}:{index}")
    assert "Эта кнопка больше не действует" in j.ui.sent[-1].text
    assert await j.ui.state.get_data() == before
    assert not j.calls("POST", CREATE)


@pytest.mark.parametrize(
    "failure",
    [*range(400, 405), 409, 429, 500, "timeout", "network", "json", "dto"],
)
async def test_read_failure_has_fresh_read_retry_and_stale_button_cannot_write(
    expense_journey: ExpenseJourney, failure: int | str
) -> None:
    j = expense_journey
    await j.simple()
    await j.ui.send("/cancel")
    await j.ui.click("menu:groups")
    await j.choose("Группа 100 · #100")
    path = "/internal/groups/100/members"
    failures: dict[str, httpx.Response | Exception] = {
        "timeout": httpx.ReadTimeout("private diagnostic"),
        "network": httpx.ConnectError("private diagnostic"),
        "json": httpx.Response(200, content=b"invalid json"),
        "dto": httpx.Response(200, json={"items": "wrong"}),
    }
    response = (
        httpx.Response(failure) if isinstance(failure, int) else failures[failure]
    )
    j.server.overrides["GET", path] = [response]
    old = await j.choose("Все участники")
    fresh = j.button("Повторить просмотр")
    assert fresh != old
    await j.ui.click(old)
    assert not j.server.saved
    count = len(j.calls("GET", path))
    await j.ui.click(fresh)
    assert len(j.calls("GET", path)) == count + 1
    assert "Участники:" in j.text
    assert not j.calls("POST", CREATE)


async def test_rate_limit_is_clear_and_keeps_frozen_intent(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    j.server.overrides["POST", CREATE] = [httpx.Response(429)]
    await j.choose("Подтвердить расход")
    frozen = await load(j.ui.state)
    assert "Слишком много запросов" in j.text
    assert frozen.request_key and frozen.sent_body
    assert len(j.calls("POST", CREATE)) == 1
    await j.choose("Повторить исходный запрос")
    writes = j.calls("POST", CREATE)
    assert len(writes) == 2 and writes[0].content == writes[1].content


async def test_unexpected_mutation_group_is_uncertain_and_not_displayed(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Серверный предпросмотр")
    foreign = copy.deepcopy(j.server.preview_data)
    private = secrets.token_urlsafe(32)
    foreign.update(
        id=999,
        group_id=999,
        title=private,
        version=1,
        created_at="2026-11-02T00:00:00Z",
        client_request_id=str(uuid4()),
        deleted_at=None,
    )
    j.server.overrides["POST", CREATE] = [
        httpx.Response(201, json={"expense": foreign, "balances": None})
    ]
    await j.choose("Подтвердить расход")
    assert await j.ui.state.get_state() == ExpenseFlow.post_uncertain.state
    assert (await load(j.ui.state)).request_key
    assert not j.calls("GET", "/internal/expenses/999")
    assert private not in j.text


@pytest.mark.parametrize("kind", ["network", "json", "dto", "server"])
async def test_unknown_write_result_keeps_exact_json_without_automatic_retry(
    expense_journey: ExpenseJourney, kind: str
) -> None:
    j = expense_journey
    await j.receipt()
    await j.choose("Серверный предпросмотр")
    failures: dict[str, httpx.Response | Exception] = {
        "network": httpx.ConnectError("private"),
        "json": httpx.Response(201, content=b"{"),
        "dto": httpx.Response(201, json={"expense": {}}),
        "server": httpx.Response(503),
    }
    j.server.overrides["POST", CREATE] = [failures[kind]]
    await j.choose("Подтвердить расход")
    frozen = await load(j.ui.state)
    await j.ui.send("/help")
    await j.ui.send("/start")
    assert (await load(j.ui.state)).sent_body == frozen.sent_body
    assert len(j.calls("POST", CREATE)) == 1
    await j.choose("Повторить исходный запрос")
    bodies = [json.loads(r.content) for r in j.calls("POST", CREATE)]
    assert bodies[0] == bodies[1] and len(j.server.saved) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 429, 500, 503])
async def test_notification_claim_failure_cannot_retry_finance_or_leak(
    settlement_journey: SettlementJourney,
    status: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    j = settlement_journey
    private = secrets.token_urlsafe(48)
    j.server.notification_chat = 987654321
    path = "/internal/settlements/123/notification-claim"
    j.server.overrides["POST", path] = [
        httpx.Response(
            status,
            json={
                "error": {"code": "unknown", "message": private, "request_id": private},
            },
        )
    ]
    with caplog.at_level(logging.DEBUG):
        await j.draft()
        await j.choose("Да, я уже перевёл деньги")
        await j.choose("История переводов")
    assert len(j.calls("POST", "/internal/groups/10/settlements")) == 1
    assert len(j.calls("POST", path)) == 1
    assert j.server.saved[123]["status"] == "pending"
    assert "Актуальный статус API: pending" in j.text
    assert not any(
        getattr(c.args[1], "text", None) == NOTICE for c in j.ui.session.await_args_list
    )
    assert private not in caplog.text + j.text
    assert "987654321" not in caplog.text + j.text


async def test_settlement_rate_limit_preserves_uuid_until_explicit_retry(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    path = "/internal/groups/10/settlements"
    await j.draft()
    j.server.overrides["POST", path] = [httpx.Response(429)]
    await j.choose("Да, я уже перевёл деньги")
    assert "Слишком много запросов" in j.text
    assert len(j.calls("POST", path)) == 1 and not j.server.saved
    await j.choose("Повторить исходную заявку")
    writes = j.calls("POST", path)
    assert len(writes) == 2 and writes[0].content == writes[1].content
    assert len(j.server.saved) == 1
