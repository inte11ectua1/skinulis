"""Accepted T-08 one-shot delivery with mocked HTTP and Telegram transports."""

import asyncio
import json
import logging
import secrets
from typing import Any

import httpx
import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import SendMessage
from pydantic import SecretStr, ValidationError

from app.schemas.settlements import NotificationClaim as BackendClaim
from bot.api_client import ApiClient, ApiError
from bot.main import create_dispatcher
from bot.settlement_dto import NotificationClaim
from bot.settlement_notifications import NOTICE
from tests.unit.test_bot_settlements import ROOT, SettlementJourney
from tests.unit.test_bot_settlements import settlement_journey as settlement_journey

pytestmark = pytest.mark.anyio
CLAIM = "/internal/settlements/123/notification-claim"
CREATE = "/internal/groups/10/settlements"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def notices(j: SettlementJourney) -> list[SendMessage]:
    return [
        call.args[1]
        for call in j.ui.session.await_args_list
        if isinstance(call.args[1], SendMessage) and call.args[1].text == NOTICE
    ]


async def test_verified_recipient_and_no_claim_on_reads_or_duplicate_update(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    j.server.notification_chat = 987654321
    await j.draft()
    assert not j.calls("POST", CLAIM)
    old = await j.choose("Да, я уже перевёл деньги")
    assert [m.chat_id for m in notices(j)] == [987654321]
    assert notices(j)[0].reply_markup is None
    assert "500.00" not in NOTICE and "могла" in NOTICE
    assert len(j.calls("POST", CREATE)) == len(j.calls("POST", CLAIM)) == 1
    request = j.calls("POST", CLAIM)[0]
    assert not request.content and request.headers["X-Telegram-ID"] == "123"
    ordered = [r.url.path for r in j.server.requests]
    assert ordered.index(CREATE) < ordered.index(CLAIM) < len(ordered) - 1
    assert ordered[-1] == "/internal/users/me"
    await j.ui.click(old)
    await j.choose("История переводов")
    await j.choose("Открыть перевод #123")
    # Reuse an already processed update_id, then simulate MemoryStorage loss.
    update = j.ui.update_id
    j.ui.update_id -= 1
    await j.ui.send("/start")
    assert j.ui.update_id == update
    await j.ui.dispatcher.fsm.close()
    j.ui.dispatcher = create_dispatcher()
    await j.ui.send("/start")
    assert len(j.calls("POST", CLAIM)) == len(notices(j)) == 1


@pytest.mark.parametrize("failure", ["blocked", "network", "timeout", "os", "deadline"])
async def test_delivery_failure_keeps_pending_and_never_reposts_or_leaks(
    settlement_journey: SettlementJourney,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    j = settlement_journey
    secret = secrets.token_urlsafe(48)
    j.server.notification_chat = 987654321
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("bot.settlement_notifications.DELIVERY_TIMEOUT", 0.01)

    async def respond(_bot: Any, method: Any, **_kwargs: Any) -> bool:
        if isinstance(method, SendMessage) and method.text == NOTICE:
            if failure == "deadline":
                await asyncio.sleep(1)
            elif failure == "blocked":
                raise TelegramForbiddenError(method=method, message=secret)
            elif failure == "network":
                raise TelegramNetworkError(method=method, message=secret)
            elif failure == "os":
                raise OSError(secret)
            else:
                raise TimeoutError(secret)
        return True

    j.ui.session.side_effect = respond
    before = json.dumps(j.server.balances_data)
    await j.draft()
    await j.choose("Да, я уже перевёл деньги")
    assert j.server.saved[123]["status"] == "pending"
    assert json.dumps(j.server.balances_data) == before
    assert len(j.calls("POST", CREATE)) == len(j.calls("POST", CLAIM)) == 1
    assert len(notices(j)) == 1
    assert "settlement_session" not in await j.ui.state.get_data()
    assert "Актуальный статус API: pending" in j.text
    for private in [secret, "987654321"]:
        assert private not in caplog.text + j.text
    assert "Pending notification delivery unavailable" in caplog.text
    await j.choose("История переводов")
    assert len(notices(j)) == 1


async def test_no_binding_consumes_claim_but_incoming_menu_still_works(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    await j.draft()
    await j.choose("Да, я уже перевёл деньги")
    assert not notices(j) and j.server.claimed == {123}
    assert len(j.calls("POST", CREATE)) == 1
    j.server.owner = 10
    await j.group()
    await j.choose("Ожидают подтверждения")
    assert "Открыть перевод #123" in str(j.ui.sent[-1].reply_markup)
    assert len(j.calls("POST", CLAIM)) == 1


@pytest.mark.parametrize("terminal", [None, "confirmed", "rejected", "cancelled"])
async def test_lost_create_recovery_claims_once_and_terminal_replay_never_sends(
    settlement_journey: SettlementJourney, terminal: str | None
) -> None:
    j = settlement_journey
    j.server.notification_chat = 987654321
    await j.draft()
    j.server.fail_after = "create"
    await j.choose("Да, я уже перевёл деньги")
    assert not j.calls("POST", CLAIM) and not notices(j)
    if terminal:
        j.server.saved[123].update(status=terminal, resolved_at="2026-10-30T12:01:00Z")
    await j.choose("Повторить исходную заявку")
    posts = j.calls("POST", CREATE)
    assert len(posts) == 2 and posts[0].content == posts[1].content
    assert len(j.calls("POST", CLAIM)) == 1
    assert len(notices(j)) == (0 if terminal else 1)
    assert f"Актуальный статус API: {terminal or 'pending'}" in j.text


@pytest.mark.parametrize("kind", ["server", "timeout", "network", "malformed"])
async def test_claim_error_has_no_send_or_financial_retry(
    settlement_journey: SettlementJourney, kind: str
) -> None:
    j = settlement_journey
    failures: dict[str, httpx.Response | Exception] = {
        "server": httpx.Response(503),
        "timeout": httpx.ReadTimeout("private"),
        "network": httpx.ConnectError("private"),
        "malformed": httpx.Response(200, json={"recipient_telegram_id": True}),
    }
    j.server.overrides["POST", CLAIM] = [failures[kind]]
    await j.draft()
    await j.choose("Да, я уже перевёл деньги")
    assert not notices(j)
    assert len(j.calls("POST", CREATE)) == len(j.calls("POST", CLAIM)) == 1
    assert j.server.saved[123]["status"] == "pending"
    assert "Актуальный статус API: pending" in j.text


@pytest.mark.parametrize("status", [200, 204])
async def test_typed_claim_wire_empty_body_sender_and_private_identity(
    status: int,
) -> None:
    calls: list[httpx.Request] = []
    fixture = json.loads(
        (ROOT / "docs/finance/fixtures/O-07N_NOTIFICATION_CLAIM.json").read_text(
            "utf-8"
        )
    )
    secret = secrets.token_urlsafe(48)

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "POST" and request.url.path == CLAIM
        assert not request.content and not request.url.params
        assert request.headers["X-Telegram-ID"] == "123"
        assert request.headers["X-Bot-Service-Token"] == secret
        assert "authorization" not in request.headers
        return (
            httpx.Response(status, json=fixture)
            if status == 200
            else httpx.Response(204)
        )

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        result = await api.claim_settlement_notification(123, 123)
        if status == 200:
            assert result is not None
            assert result.recipient_telegram_id == fixture["recipient_telegram_id"]
            BackendClaim.model_validate_json(result.model_dump_json())
            assert str(result.recipient_telegram_id) not in repr(result)
        else:
            assert result is None
    assert api.is_closed and len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"null"),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"recipient_telegram_id": "123"}),
        httpx.Response(200, json={"recipient_telegram_id": True}),
        httpx.Response(200, json={"recipient_telegram_id": -123}),
        httpx.Response(200, json={"recipient_telegram_id": 2**63}),
        httpx.Response(200, json={"recipient_telegram_id": 123, "extra": 1}),
        httpx.Response(204, content=b"{}"),
        httpx.Response(201, json={"recipient_telegram_id": 123}),
        *[
            httpx.Response(status)
            for status in [400, 401, 403, 404, 409, 429, 500, 503]
        ],
    ],
)
async def test_claim_rejects_noncontract_responses_without_retry(
    response: httpx.Response,
) -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(respond),
    ) as api:
        with pytest.raises(ApiError):
            await api.claim_settlement_notification(123, 123)
    assert calls == 1


async def test_claim_id_validation_hides_input() -> None:
    with pytest.raises(ValidationError):
        NotificationClaim(recipient_telegram_id=0)
