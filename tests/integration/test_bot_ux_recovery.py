"""Real committed writes with deliberate loss/corruption at the HTTP boundary."""

import json
import secrets
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import httpx
import pytest
from aiogram.types import InlineKeyboardMarkup
from pydantic import SecretStr

from app.config import Settings
from bot.api_client import ApiError
from bot.expense_dto import DRAFT, draft_from_profile
from bot.expense_wizard import load
from bot.main import create_dispatcher
from bot.settlement_dto import SettlementCreate
from bot.states import ExpenseFlow
from tests.integration.test_bot_expenses import LostResponse, fill, open_wizard
from tests.integration.test_bot_expenses import finance_ui as finance_ui
from tests.integration.test_bot_identity_groups import choose
from tests.integration.test_bot_identity_groups import local_api as local_api
from tests.integration.test_bot_settlements import Restaurant
from tests.integration.test_bot_settlements import restaurant as restaurant
from tests.unit.test_bot_handlers import Harness

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("mode", ["equal", "custom", "by_items"])
@pytest.mark.parametrize("failure", ["network", "json", "dto"])
async def test_committed_expense_replay_reads_edited_or_deleted_current_state(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
    mode: str,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui, transport, ids, gid = finance_ui
    original: Callable[[httpx.Request], Awaitable[httpx.Response]] = (
        transport.handle_async_request
    )
    armed = True

    async def damage(request: httpx.Request) -> httpx.Response:
        nonlocal armed
        response = await original(request)
        if (
            armed
            and request.method == "POST"
            and request.url.path.endswith("/expenses")
        ):
            armed = False
            assert response.status_code == 201
            await response.aread()
            await response.aclose()
            if failure == "network":
                raise httpx.ReadError("Synthetic private transport diagnostic")
            return httpx.Response(
                201, content=b"{" if failure == "json" else b'{"expense":{}}'
            )
        return response

    monkeypatch.setattr(transport, "handle_async_request", damage)
    await open_wizard(ui, gid, mode)
    await fill(ui, mode, ids)
    await choose(ui, "Проверить доли")
    await choose(ui, "Подтвердить расход")
    assert await ui.state.get_state() == ExpenseFlow.post_uncertain.state
    frozen = await load(ui.state)
    writes = [
        w for w in transport.writes if w[0] == "POST" and w[1].endswith("/expenses")
    ]
    assert len(writes) == 1  # No automatic retry despite the committed record.
    record = (await ui.api.expenses(123, gid)).items[0]
    business = draft_from_profile(record)
    if failure == "json":
        await ui.api.delete_expense(123, record.id, record.version)
    else:
        await ui.api.update_expense(
            123,
            record.id,
            business.model_copy(update={"title": "Актуальная версия"}),
            record.version,
        )
    markup = ui.sent[-1].reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    button = next(
        b.callback_data
        for row in markup.inline_keyboard
        for b in row
        if b.text == "Повторить исходный запрос"
    )
    assert button is not None
    await ui.send("/help")
    await ui.send("/start")
    assert (await load(ui.state)).sent_body == frozen.sent_body
    start = len(ui.sent)
    await ui.click(button)
    await ui.click(button)
    writes = [
        w for w in transport.writes if w[0] == "POST" and w[1].endswith("/expenses")
    ]
    assert len(writes) == 2 and writes[0][2] == writes[1][2]
    text = " ".join(m.text for m in ui.sent[start:])
    if failure == "json":
        assert "недоступна" in text and "Сохранённый расход" not in text
        assert not (await ui.api.expenses(123, gid)).items
    else:
        assert "Актуальная версия" in text
        current = (await ui.api.expenses(123, gid)).items
        assert current[0].version == 2
        assert len((await ui.api.expenses(123, gid)).items) == 1
    # Changed intent with the original UUID must remain a conflict, never a duplicate.
    changed = business.model_copy(update={"title": "Другое намерение"})
    assert frozen.request_key is not None
    with pytest.raises(ApiError) as conflict:
        await ui.api.create_expense(123, gid, changed, UUID(frozen.request_key))
    assert conflict.value.error_code == "request_conflict"
    assert json.loads(writes[0][2])["client_request_id"] == frozen.request_key


async def test_real_401_keeps_draft_then_same_intent_succeeds_once(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
    local_api: tuple[str, Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui, transport, ids, gid = finance_ui
    await open_wizard(ui, gid, "custom")
    await fill(ui, "custom", ids)
    original = (await load(ui.state)).business()
    await choose(ui, "Проверить доли")
    with monkeypatch.context() as invalid:
        invalid.setattr(ui.api, "_service_token", SecretStr(secrets.token_urlsafe(48)))
        await choose(ui, "Подтвердить расход")
    assert (await load(ui.state)).business() == original
    assert not (await ui.api.expenses(123, gid)).items
    await choose(ui, "Проверить доли")
    await choose(ui, "Подтвердить расход")
    writes = [
        w for w in transport.writes if w[0] == "POST" and w[1].endswith("/expenses")
    ]
    assert len(writes) == 2 and writes[0][2] == writes[1][2]
    assert len((await ui.api.expenses(123, gid)).items) == 1


async def test_cancel_and_restart_after_actual_commit_do_not_undo_or_repost(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
) -> None:
    ui, transport, ids, gid = finance_ui
    await open_wizard(ui, gid, "equal")
    await fill(ui, "equal", ids)
    await choose(ui, "Проверить доли")
    transport.lose = "POST"
    await choose(ui, "Подтвердить расход")
    screen = (await ui.state.get_data())["screen"]
    await ui.send("/cancel")
    assert "Сохранённые записи не отменяются" in " ".join(m.text for m in ui.sent)
    assert "expense_session" not in await ui.state.get_data()
    await ui.dispatcher.fsm.close()
    ui.dispatcher = create_dispatcher()
    try:
        await ui.send("/start")
        await ui.click(f"l3:{screen}:0")
        assert ui.alerts[-1].show_alert
        assert "Используйте последние кнопки" in str(ui.alerts[-1].text)
        assert len((await ui.api.expenses(123, gid)).items) == 1
        assert (
            len(
                [
                    w
                    for w in transport.writes
                    if w[0] == "POST" and w[1].endswith("/expenses")
                ]
            )
            == 1
        )
    finally:
        await ui.dispatcher.fsm.close()


async def test_real_access_actor_body_and_mixed_channel_denials(
    restaurant: Restaurant,
    local_api: tuple[str, Settings],
) -> None:
    r = restaurant
    base, settings = local_api
    # Anton becomes a creditor; owner Timur is neither party to this transfer.
    await r.api.create_expense(
        456,
        r.gid,
        DRAFT.validate_python(
            {
                "title": "Оплатил Антон",
                "split_mode": "equal",
                "amount": "2000.00",
                "participants": [r.ids[2]],
            }
        ),
        uuid4(),
    )
    record = (
        await r.api.create_settlement(
            789,
            r.gid,
            SettlementCreate(
                receiver_id=r.ids[1],
                amount="100.00",
                client_request_id=uuid4(),
            ),
        )
    ).settlement
    before = await r.vector()
    for actor, method in [
        (123, r.api.confirm_settlement),
        (456, r.api.cancel_settlement),
        (789, r.api.reject_settlement),
    ]:
        with pytest.raises(ApiError) as denied:
            await method(actor, record.id)
        assert denied.value.status_code == 403
    await r.open(r.owner, record.id)
    assert "Подтвердить получение" not in str(r.owner.sent[-1].reply_markup)
    count = len(r.transport.posts)
    await r.owner.click(f"st:ask:{r.gid}:{record.id}:confirm:789")
    await r.owner.click("l3:forged:999", user_id=789)
    assert len(r.transport.posts) == count
    with pytest.raises(ApiError) as foreign_group:
        await r.api.group(999, r.gid)
    assert foreign_group.value.status_code == 404
    with pytest.raises(ApiError) as foreign_expense:
        await r.api.expense(999, r.eid)
    assert foreign_expense.value.status_code == 404
    with pytest.raises(ApiError) as author:
        await r.api.update_expense(
            456,
            r.eid,
            DRAFT.validate_python(
                {
                    "title": "Чужое",
                    "split_mode": "equal",
                    "amount": "1.00",
                    "participants": [r.ids[1]],
                }
            ),
            1,
        )
    assert author.value.status_code == 403
    headers = {
        "X-Bot-Service-Token": settings.require_bot_service_token(),
        "X-Telegram-ID": "456",
    }
    async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=10) as raw:
        for extra in [
            {"Authorization": "Bearer synthetic"},
            {"X-Bot-Service-Token": secrets.token_urlsafe(48)},
        ]:
            response = await raw.get(
                f"/internal/groups/{r.gid}", headers=headers | extra
            )
            assert response.status_code == (400 if "Authorization" in extra else 401)
            assert "Ресторан" not in response.text
        response = await raw.post(
            f"/internal/groups/{r.gid}/settlements",
            headers=headers,
            json={
                "receiver_id": r.ids[0],
                "amount": "1.00",
                "client_request_id": str(uuid4()),
                "telegram_id": 123,
            },
        )
        assert response.status_code == 400
    assert await r.vector() == before
    assert (await r.api.settlements(456, r.gid)).items[0].status == "pending"
