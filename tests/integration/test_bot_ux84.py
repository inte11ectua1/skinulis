"""Redesigned names + equal/custom journeys through real HTTP/PostgreSQL, no Telegram."""

import pytest
from aiogram.methods import SendMessage

from bot.presentation import money
from tests.integration.test_bot_expenses import (
    LostResponse,
    choose,
    open_wizard,
)
from tests.integration.test_bot_expenses import finance_ui as finance_ui
from tests.integration.test_bot_identity_groups import local_api as local_api
from tests.integration.test_bot_settlements import Restaurant
from tests.integration.test_bot_settlements import restaurant as restaurant
from tests.unit.test_bot_handlers import Harness

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_named_equal_100_and_custom_10_keep_real_financial_contract(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
) -> None:
    ui, transport, ids, gid = finance_ui
    for actor, name in [(123, "Антон"), (456, "Саша"), (789, "Саша")]:
        await ui.api.rename_profile(actor, name)
    for mode, raw, amount, shares in [
        ("equal", "100", "100.00", ["33.34", "33.33", "33.33"]),
        ("custom", "10,0", "10.00", ["0.00", "3.33", "6.67"]),
    ]:
        await open_wizard(ui, gid, mode)
        await ui.send("Тестовая поездка")
        await ui.send(raw)
        sends = sum(
            isinstance(c.args[1], SendMessage) for c in ui.session.await_args_list
        )
        await choose(ui, "Выбрать всех")
        await choose(ui, f"@ex:toggle:{ids[2]}")
        await choose(ui, "Снять выбор")
        await choose(ui, "Готово")
        assert "Выбрано: 0 из 3" in ui.sent[-1].text
        await choose(ui, "Выбрать всех")
        assert (
            sum(isinstance(c.args[1], SendMessage) for c in ui.session.await_args_list)
            == sends
        )
        markup = str(ui.sent[-1].reply_markup)
        assert "Саша · А" in markup and "Саша · Б" in markup
        await choose(ui, "Готово")
        if mode == "custom":
            for share in ["0,00", "3,33", "6.67"]:
                await ui.send(share)
        await choose(ui, "Проверить доли")
        assert not (await ui.api.expenses(123, gid)).items
        for share in shares:
            assert money(share) in ui.sent[-1].text
        stale = await choose(ui, "Подтвердить расход")
        await ui.click(stale)
        saved = (await ui.api.expenses(123, gid)).items
        assert len(saved) == 1 and saved[0].amount == amount
        assert [s.amount for s in saved[0].shares] == shares
        assert "Антон" in ui.sent[-1].text and "Участник #" not in ui.sent[-1].text
        if mode == "equal":
            await choose(ui, "Редактировать")
            await choose(ui, "Продолжить редактирование")
            await choose(ui, "Изменить сумму")
            await ui.send("100,5")
            await choose(ui, "Проверить доли")
            await choose(ui, "Сохранить изменения")
            updated = await ui.api.expense(123, saved[0].id)
            assert updated.amount == "100.50"
            assert [s.amount for s in updated.shares] == ["33.50"] * 3
            saved = [updated]
        await ui.api.delete_expense(123, saved[0].id, saved[0].version)
        assert all(
            b.balance == "0.00" for b in (await ui.api.balances(123, gid)).balances
        )
    assert (
        len(
            [
                w
                for w in transport.writes
                if w[0] == "POST" and w[1].endswith("/expenses")
            ]
        )
        == 2
    )


async def test_human_receipt_kopeck_retries_exactly_once(
    finance_ui: tuple[Harness, LostResponse, list[int], int],
) -> None:
    ui, transport, _, gid = finance_ui
    await open_wizard(ui, gid, "by_items")
    await ui.send("Чек")
    await ui.send("Пробная позиция")
    await ui.send("0,01")
    await choose(ui, "Выбрать всех")
    await choose(ui, "Готово")
    await choose(ui, "Проверить доли")
    transport.lose = "POST"
    await choose(ui, "Подтвердить расход")
    await choose(ui, "Повторить исходный запрос")
    records = (await ui.api.expenses(123, gid)).items
    assert len(records) == 1 and records[0].amount == "0.01"
    assert [s.amount for s in records[0].shares] == ["0.01", "0.00", "0.00"]
    writes = [w for w in transport.writes if w[1].endswith("/expenses")]
    assert len(writes) == 2 and writes[0][2] == writes[1][2]


async def test_human_transfer_preserves_cents_and_post_timeout_intent(
    restaurant: Restaurant,
) -> None:
    r = restaurant
    before = await r.vector()
    await r.draft("100,5")
    r.transport.drop = "create"
    await choose(r.sender, "Да, я уже перевёл деньги")
    await choose(r.sender, "Повторить исходную заявку")
    records = (await r.api.settlements(456, r.gid)).items
    assert len(records) == 1 and records[0].amount == "100.50"
    assert await r.vector() == before  # Pending never changes the server balance.
    posts = [p for p in r.transport.posts if p[0].endswith("/settlements")]
    assert len(posts) == 2
    assert posts[0][1] == posts[1][1]
