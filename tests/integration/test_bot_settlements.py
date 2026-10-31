"""M4 UI → actual loopback HTTP/PostgreSQL17. Only Telegram is mocked."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from bot.api_client import ApiClient, ApiError
from bot.dto import GroupDraft
from bot.expense_dto import DRAFT
from bot.main import create_dispatcher
from bot.settlement_dto import SettlementCreate, SettlementProfile
from tests.integration.test_bot_expenses import choose
from tests.integration.test_bot_identity_groups import local_api as local_api
from tests.integration.test_bot_identity_groups import telegram
from tests.unit.test_bot_handlers import Harness

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class LostResponse(httpx.AsyncBaseTransport):
    """Discard an actual post-commit response, never fake the API or its balances."""

    def __init__(self) -> None:
        self.http = httpx.AsyncHTTPTransport()
        self.drop: str | None = None
        self.posts: list[tuple[str, bytes, str]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.http.handle_async_request(request)
        if request.method == "POST" and "settlements" in request.url.path:
            self.posts.append(
                (request.url.path, request.content, request.headers["X-Telegram-ID"])
            )
            operation = (
                "create"
                if request.url.path.endswith("/settlements")
                else request.url.path.rsplit("/", 1)[1]
            )
            if self.drop == operation:
                self.drop = None
                await response.aread()
                await response.aclose()
                raise httpx.ReadTimeout("Discarded an actual committed test response")
        return response

    async def aclose(self) -> None:
        await self.http.aclose()


@dataclass
class Restaurant:
    api: ApiClient
    owner: Harness
    sender: Harness
    other: Harness
    transport: LostResponse
    ids: list[int]
    gid: int
    eid: int

    async def group(self, ui: Harness) -> None:
        await ui.send("/start")
        await ui.click("menu:groups")
        await choose(ui, f"Ресторан M4 · #{self.gid}")

    async def draft(self, amount: str = "500.00") -> None:
        await self.group(self.sender)
        await choose(self.sender, "План переводов")
        await choose(self.sender, "Я перевёл деньги")
        await choose(self.sender, f"Участник #{self.ids[0]}")
        await self.sender.send(amount)

    async def mark(self, amount: str = "500.00") -> SettlementProfile:
        await self.draft(amount)
        await choose(self.sender, "Да, я уже перевёл деньги")
        return (await self.api.settlements(456, self.gid, direction="outgoing")).items[
            -1
        ]

    async def open(self, ui: Harness, sid: int) -> None:
        await self.group(ui)
        await choose(ui, "История переводов")
        await choose(ui, f"Открыть перевод #{sid}")

    async def vector(self) -> list[str]:
        return [b.balance for b in (await self.api.balances(123, self.gid)).balances]


@pytest.fixture
async def restaurant(local_api: tuple[str, Settings]) -> AsyncIterator[Restaurant]:
    base, settings = local_api
    bot, dispatcher, transport = telegram(), create_dispatcher(), LostResponse()
    async with ApiClient(
        base, service_token=settings.bot_service_token, transport=transport
    ) as api:
        users = [await api.bootstrap(actor) for actor in [123, 456, 789, 999]]
        ids = [u.id for u in users]
        group = await api.create_group(
            123, GroupDraft(name="Ресторан M4", client_request_id=uuid4())
        )
        for actor in [456, 789]:
            invite = await api.issue_invite(123, group.id, uuid4())
            assert invite.token is not None
            await api.join(actor, invite.token)
        receipt = DRAFT.validate_python(
            {
                "title": "Ресторан",
                "split_mode": "by_items",
                "items": [
                    {"title": "Паста", "amount": "700.00", "participants": ids[:1]},
                    {"title": "Стейк", "amount": "1100.00", "participants": ids[1:2]},
                    {"title": "Салат", "amount": "500.00", "participants": ids[2:3]},
                    {"title": "Пицца", "amount": "900.00", "participants": ids[:3]},
                ],
            }
        )
        expense = (await api.create_expense(123, group.id, receipt, uuid4())).expense

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

        try:
            yield Restaurant(
                api, ui(123), ui(456), ui(789), transport, ids, group.id, expense.id
            )
        finally:
            await dispatcher.fsm.close()
            await bot.session.close()


async def test_restaurant_partial_confirm_repeat_and_soft_delete_reverse_debt(
    restaurant: Restaurant,
) -> None:
    r = restaurant
    assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]
    await r.group(r.sender)
    await choose(r.sender, "Балансы")
    assert "-1400.00 ₽ — участник должен" in " ".join(m.text for m in r.sender.sent)
    pending = await r.mark()
    assert pending.status == "pending" and await r.vector() == [
        "2200.00",
        "-1400.00",
        "-800.00",
    ]
    await r.owner.send("/start")
    await r.owner.click("menu:pending")
    await choose(r.owner, f"Ресторан M4 · #{r.gid}")
    await choose(r.owner, f"Открыть перевод #{pending.id}")
    await choose(r.owner, "Подтвердить получение")
    assert "реально полученные деньги" in r.owner.sent[-1].text
    old = await choose(r.owner, "Да, деньги получены")
    await r.owner.click(old)
    confirmed = (await r.api.settlements(123, r.gid, status="confirmed")).items[0]
    assert await r.vector() == ["1700.00", "-900.00", "-800.00"]
    repeat = await r.api.confirm_settlement(123, pending.id)
    assert repeat.settlement.resolved_at == confirmed.resolved_at
    assert await r.vector() == ["1700.00", "-900.00", "-800.00"]
    text = " ".join(m.text for m in r.owner.sent)
    assert "1700.00" in text and "-900.00" in text
    assert f"Участник #{r.ids[1]} → Участник #{r.ids[0]}: 900.00 ₽" in text
    # Exercise the existing L-04 UI with actual confirmed history, no bot balance math.
    await choose(r.owner, "К группе")
    await choose(r.owner, "Расходы")
    await choose(r.owner, f"Открыть #{r.eid} · Ресторан")
    await choose(r.owner, "Удалить")
    assert "обратного долга" in r.owner.sent[-1].text
    await choose(r.owner, "Да, удалить расход")
    assert await r.vector() == ["-500.00", "500.00", "0.00"]
    assert (await r.api.settlements(123, r.gid)).items[0].status == "confirmed"
    await choose(r.owner, "К группе")
    await choose(r.owner, "Балансы")
    text = " ".join(m.text for m in r.owner.sent)
    assert "-500.00 ₽ — участник должен" in text and "0.00 ₽ — долгов нет" in text


async def test_two_pending_full_debt_only_one_confirms_other_can_reject(
    restaurant: Restaurant,
) -> None:
    r = restaurant
    first, second = await r.mark("1400.00"), await r.mark("1400.00")
    assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]
    await r.open(r.owner, first.id)
    await choose(r.owner, "Подтвердить получение")
    await choose(r.owner, "Да, деньги получены")
    await choose(r.owner, "Ожидают подтверждения")
    await choose(r.owner, f"Открыть перевод #{second.id}")
    await choose(r.owner, "Подтвердить получение")
    await choose(r.owner, "Да, деньги получены")
    rows = (await r.api.settlements(123, r.gid)).items
    assert [v.status for v in rows] == ["confirmed", "pending"]
    assert "Долг или доступный кредит изменился" in " ".join(
        m.text for m in r.owner.sent
    )
    assert await r.vector() == ["800.00", "0.00", "-800.00"]
    await choose(r.owner, "Отклонить")
    await choose(r.owner, "Да, отклонить")
    assert (await r.api.settlements(123, r.gid)).items[-1].status == "rejected"
    assert await r.vector() == ["800.00", "0.00", "-800.00"]


async def test_changed_expense_before_confirm_conflicts_without_amount_repair(
    restaurant: Restaurant,
) -> None:
    r = restaurant
    record = await r.mark("1400.00")
    await r.api.update_expense(
        123,
        r.eid,
        DRAFT.validate_python(
            {
                "title": "Уменьшено",
                "split_mode": "equal",
                "amount": "1000.00",
                "participants": r.ids[1:2],
            }
        ),
        1,
    )
    await r.open(r.owner, record.id)
    await choose(r.owner, "Подтвердить получение")
    await choose(r.owner, "Да, деньги получены")
    current = (await r.api.settlements(123, r.gid)).items[0]
    assert (
        current.status == "pending"
        and current.amount == "1400.00"
        and current.resolved_at is None
    )
    assert await r.vector() == ["1000.00", "-1000.00", "0.00"]
    assert "Прежнюю сумму сейчас принять нельзя" in " ".join(
        m.text for m in r.owner.sent
    )


@pytest.mark.parametrize("operation", ["reject", "cancel"])
async def test_reject_cancel_immutability_wrong_roles_and_foreign_access(
    restaurant: Restaurant, operation: str
) -> None:
    r = restaurant
    record = await r.mark()
    for actor, method, code in [
        (789, r.api.confirm_settlement, "settlement_receiver_required"),
        (123, r.api.cancel_settlement, "settlement_sender_required"),
    ]:
        with pytest.raises(ApiError) as wrong:
            await method(actor, record.id)
        assert wrong.value.status_code == 403 and wrong.value.error_code == code
    with pytest.raises(ApiError) as foreign:
        await r.api.settlements(999, r.gid)
    assert foreign.value.status_code == 404
    ui = r.owner if operation == "reject" else r.sender
    await r.open(ui, record.id)
    await choose(ui, "Отклонить" if operation == "reject" else "Отменить заявку")
    await choose(
        ui, "Да, отклонить" if operation == "reject" else "Да, отменить заявку"
    )
    method = (
        r.api.reject_settlement if operation == "reject" else r.api.cancel_settlement
    )
    repeated = await method(123 if operation == "reject" else 456, record.id)
    assert repeated.settlement.status == (
        "rejected" if operation == "reject" else "cancelled"
    )
    with pytest.raises(ApiError) as conflict:
        await r.api.confirm_settlement(123, record.id)
    assert conflict.value.error_code == "settlement_state_conflict"
    assert await r.vector() == ["2200.00", "-1400.00", "-800.00"]


@pytest.mark.parametrize("operation", ["create", "confirm", "reject", "cancel"])
async def test_real_response_lost_after_commit_and_historical_replay(
    restaurant: Restaurant, operation: str
) -> None:
    r = restaurant
    if operation == "create":
        await r.draft()
        r.transport.drop = "create"
        await choose(r.sender, "Да, я уже перевёл деньги")
        current = (await r.api.settlements(123, r.gid)).items[0]
        await r.api.confirm_settlement(123, current.id)
        await choose(r.sender, "История переводов")
        await choose(r.sender, "К восстановлению заявки")
        await choose(r.sender, "Повторить исходную заявку")
        creates = [p for p in r.transport.posts if p[0].endswith("/settlements")]
        assert len(creates) == 2 and creates[0] == creates[1]
        body = SettlementCreate.model_validate_json(creates[0][1])
        history = await r.api.create_settlement(456, r.gid, body)
        assert (
            history.settlement.status == "pending"
            and history.settlement.resolved_at is None
        )
        text = " ".join(m.text for m in r.sender.sent)
        assert (
            "Актуальный статус API: confirmed" in text
            and "Актуальный статус API: pending" not in text
        )
        assert len((await r.api.settlements(123, r.gid)).items) == 1
    else:
        current = await r.mark()
        ui = r.sender if operation == "cancel" else r.owner
        await r.open(ui, current.id)
        await choose(
            ui,
            {
                "confirm": "Подтвердить получение",
                "reject": "Отклонить",
                "cancel": "Отменить заявку",
            }[operation],
        )
        r.transport.drop = operation
        await choose(
            ui,
            {
                "confirm": "Да, деньги получены",
                "reject": "Да, отклонить",
                "cancel": "Да, отменить заявку",
            }[operation],
        )
        text = " ".join(m.text for m in ui.sent)
        target = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}[
            operation
        ]
        assert (
            f"Актуальный статус API: {target}" in text
            and "API подтвердил статус" not in text
        )
        assert (
            len([p for p in r.transport.posts if p[0].endswith("/" + operation)]) == 1
        )


async def test_real_filters_pagination_and_sequential_current_status_lookup(
    restaurant: Restaurant,
) -> None:
    r = restaurant
    for _ in range(21):
        await r.api.create_settlement(
            456,
            r.gid,
            SettlementCreate(
                receiver_id=r.ids[0], amount="1.00", client_request_id=uuid4()
            ),
        )
    await r.group(r.owner)
    await choose(r.owner, "Ожидают подтверждения")
    await choose(r.owner, "Далее")
    page = await r.api.settlements(
        123, r.gid, status="pending", direction="incoming", offset=20
    )
    assert len(page.items) == 1
    await choose(r.owner, f"Открыть перевод #{page.items[0].id}")
    await choose(r.owner, "Следующая страница поиска")
    assert "Актуальный статус API: pending" in " ".join(m.text for m in r.owner.sent)
    await choose(r.owner, "Подтвердить получение")
    # Review itself also reads pages, never invents GET /settlements/{id}.
    await choose(r.owner, "Следующая страница поиска")
    await choose(r.owner, "Да, деньги получены")
    await choose(r.owner, "История переводов")
    await choose(r.owner, "Статус: confirmed")
    assert len((await r.api.settlements(123, r.gid, status="confirmed")).items) == 1


async def test_compensation_above_single_expense_ceiling_uses_server_limit(
    restaurant: Restaurant,
) -> None:
    r = restaurant
    for _ in range(3):
        await r.api.create_expense(
            123,
            r.gid,
            DRAFT.validate_python(
                {
                    "title": "Крупный расход",
                    "split_mode": "equal",
                    "amount": "1000000.00",
                    "participants": r.ids[1:2],
                }
            ),
            uuid4(),
        )
    pending = await r.mark("2000000.00")
    assert pending.amount == "2000000.00" and pending.status == "pending"
