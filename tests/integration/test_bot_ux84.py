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
    for mode, amount, shares in [
        ("equal", "100.00", ["33.34", "33.33", "33.33"]),
        ("custom", "10.00", ["0.00", "3.33", "6.67"]),
    ]:
        await open_wizard(ui, gid, mode)
        await ui.send("Тестовая поездка")
        await ui.send(amount)
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
            for share in shares:
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
