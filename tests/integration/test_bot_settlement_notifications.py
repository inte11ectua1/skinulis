"""Actual HTTP/PG claim and financial ledger; only Telegram delivery is mocked."""

import secrets
from typing import Any

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import URL

from app.core.security import hash_password
from app.models import Settlement, User
from bot.main import create_dispatcher
from bot.settlement_dto import SettlementCreate
from bot.settlement_notifications import NOTICE
from tests.integration.test_bot_expenses import choose
from tests.integration.test_bot_identity_groups import local_api as local_api
from tests.integration.test_bot_settlements import Restaurant
from tests.integration.test_bot_settlements import restaurant as restaurant

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def notices(r: Restaurant) -> list[SendMessage]:
    return [
        call.args[1]
        for call in r.sender.session.await_args_list
        if isinstance(call.args[1], SendMessage) and call.args[1].text == NOTICE
    ]


def claimed_at(database_url: URL, sid: int) -> Any:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                select(Settlement.notification_claimed_at).where(Settlement.id == sid)
            ).scalar_one()
    finally:
        engine.dispose()


async def test_private_binding_and_at_most_one_delivery_across_duplicate_and_restart(
    restaurant: Restaurant, database_url: URL
) -> None:
    r = restaurant
    record = await r.mark()
    assert [m.chat_id for m in notices(r)] == [123]
    assert record.receiver_id == r.ids[0] != 123
    stamp = claimed_at(database_url, record.id)
    assert stamp is not None
    assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]
    claims = [p for p in r.transport.posts if p[0].endswith("/notification-claim")]
    assert len(claims) == 1 and claims[0][1:] == (b"", "456")
    assert await r.api.claim_settlement_notification(456, record.id) is None
    await r.sender.dispatcher.fsm.close()
    r.sender.dispatcher = create_dispatcher()
    try:
        await r.open(r.sender, record.id)
        assert len(notices(r)) == 1
        assert claimed_at(database_url, record.id) == stamp
        assert len([p for p in r.transport.posts if p[0].endswith("/settlements")]) == 1
    finally:
        await r.sender.dispatcher.fsm.close()


@pytest.mark.parametrize("failure", ["blocked", "network"])
async def test_failed_telegram_preserves_pending_ledger_and_incoming_menu(
    restaurant: Restaurant,
    database_url: URL,
    failure: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = restaurant
    private = secrets.token_urlsafe(48)

    async def respond(_bot: Any, method: Any, **_kwargs: Any) -> bool:
        if isinstance(method, SendMessage) and method.text == NOTICE:
            kind = (
                TelegramForbiddenError if failure == "blocked" else TelegramNetworkError
            )
            raise kind(method=method, message=private)
        return True

    r.sender.session.side_effect = respond
    pending = await r.mark()
    assert (
        pending.status == "pending" and claimed_at(database_url, pending.id) is not None
    )
    assert len(notices(r)) == 1
    assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]
    assert len([p for p in r.transport.posts if p[0].endswith("/settlements")]) == 1
    await r.group(r.owner)
    await choose(r.owner, "Ожидают подтверждения")
    await choose(r.owner, f"Открыть перевод #{pending.id}")
    assert "Актуальный статус API: pending" in " ".join(m.text for m in r.owner.sent)
    assert private not in caplog.text + " ".join(m.text for m in r.sender.sent)


@pytest.mark.parametrize("terminal", [None, "confirm", "reject", "cancel"])
async def test_real_lost_create_recovery_and_historical_terminal_replay(
    restaurant: Restaurant, terminal: str | None
) -> None:
    r = restaurant
    await r.draft()
    r.transport.drop = "create"
    await choose(r.sender, "Да, я уже перевёл деньги")
    assert not notices(r)
    pending = (await r.api.settlements(456, r.gid, direction="outgoing")).items[0]
    if terminal:
        methods = {
            "confirm": r.api.confirm_settlement,
            "reject": r.api.reject_settlement,
            "cancel": r.api.cancel_settlement,
        }
        await methods[terminal](456 if terminal == "cancel" else 123, pending.id)
    old = await choose(r.sender, "Повторить исходную заявку")
    creates = [p for p in r.transport.posts if p[0].endswith("/settlements")]
    assert len(creates) == 2 and creates[0] == creates[1]
    assert len(notices(r)) == (0 if terminal else 1)
    expected = {
        None: "pending",
        "confirm": "confirmed",
        "reject": "rejected",
        "cancel": "cancelled",
    }[terminal]
    assert f"Актуальный статус API: {expected}" in " ".join(
        m.text for m in r.sender.sent
    )
    await r.sender.click(old)
    assert (
        len([p for p in r.transport.posts if p[0].endswith("/notification-claim")]) == 1
    )
    # The exact original POST is still historical; it cannot restore permission.
    draft = SettlementCreate.model_validate_json(creates[0][1])
    history = await r.api.create_settlement(456, r.gid, draft)
    assert history.settlement.status == "pending"
    assert await r.api.claim_settlement_notification(456, pending.id) is None
    assert len((await r.api.settlements(456, r.gid)).items) == 1


async def test_claim_response_lost_after_commit_never_sends_or_retries_finance(
    restaurant: Restaurant, database_url: URL
) -> None:
    r = restaurant
    await r.draft()
    r.transport.drop = "notification-claim"
    await choose(r.sender, "Да, я уже перевёл деньги")
    pending = (await r.api.settlements(456, r.gid)).items[0]
    assert not notices(r) and pending.status == "pending"
    stamp = claimed_at(database_url, pending.id)
    assert stamp is not None
    assert (
        len([p for p in r.transport.posts if p[0].endswith("/notification-claim")]) == 1
    )
    assert len([p for p in r.transport.posts if p[0].endswith("/settlements")]) == 1
    assert await r.api.claim_settlement_notification(456, pending.id) is None
    assert claimed_at(database_url, pending.id) == stamp
    assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]


async def test_unlinked_receiver_no_send_and_no_binding_leak(
    restaurant: Restaurant, database_url: URL
) -> None:
    r = restaurant
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                update(User)
                .where(User.id == r.ids[0])
                .values(
                    telegram_id=None,
                    email="receiver@example.test",
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                )
            )
        pending = await r.mark()
        assert not notices(r) and pending.status == "pending"
        assert claimed_at(database_url, pending.id) is not None
        with engine.begin() as connection:
            connection.execute(
                update(User).where(User.id == r.ids[0]).values(telegram_id=123)
            )
        assert await r.api.claim_settlement_notification(456, pending.id) is None
        assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]
        assert "telegram" not in pending.model_dump_json()
    finally:
        engine.dispose()
