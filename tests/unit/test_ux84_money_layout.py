"""Human input stays separate from canonical DTOs and server financial rules."""

import json
from uuid import uuid4

import pytest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup
from pydantic import ValidationError

from bot.expense_dto import DRAFT, money_input
from bot.expense_wizard import load
from bot.keyboard_layout import compact
from bot.keyboards import action_keyboard
from bot.money_input import parse_money
from bot.presentation import money
from bot.settlement_dto import SettlementCreate, amount_input
from tests.unit import test_bot_expenses as expense_tests
from tests.unit import test_bot_onboarding_groups as group_tests
from tests.unit import test_bot_settlements as settlement_tests
from tests.unit.test_bot_expenses import ExpenseJourney
from tests.unit.test_bot_onboarding_groups import Journey
from tests.unit.test_bot_settlements import SettlementJourney

expense_journey = expense_tests.expense_journey
settlement_journey = settlement_tests.settlement_journey
journey = group_tests.journey


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100", "100.00"),
        ("100,00", "100.00"),
        ("100.00", "100.00"),
        ("100,5", "100.50"),
        ("100.5", "100.50"),
        ("0,01", "0.01"),
        ("12,34", "12.34"),
        (" 100,5 ", "100.50"),
        ("\u00a0100\u202f", "100.00"),
        ("1000000", "1000000.00"),
    ],
)
def test_human_money_normalization(raw: str, expected: str) -> None:
    assert parse_money(raw) == money_input(raw) == amount_input(raw) == expected


@pytest.mark.parametrize("raw", ["0", "0,0", "0.00", "0,00"])
def test_zero_only_for_custom_share(raw: str) -> None:
    assert money_input(raw, zero=True) == "0.00"
    for parser in (money_input, amount_input):
        with pytest.raises(ValueError):
            parser(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "100,999",
        "-100",
        "+100",
        "1e3",
        "1 000",
        "1\u00a0000",
        "100руб",
        "1,2,3",
        "",
        " ",
        ".50",
        ",50",
        "100.",
        "100,",
        "01",
        "01,50",
        "1.2,3",
        "1,2.3",
        "NaN",
        "Infinity",
        "100 ₽",
        "١٠٠",
        "１００",
        "100\n",
        "\t100",
        "1_000",
        "1'000",
        "0.001",
        "0,001",
        "1\x002",
    ],
)
def test_ambiguous_money_is_rejected_without_rounding(raw: str) -> None:
    for parser in (money_input, amount_input):
        with pytest.raises(ValueError):
            parser(raw)


@pytest.mark.parametrize("raw", ["100", "100,00", "100.5", " 100.00 "])
def test_wire_dtos_remain_strict(raw: str) -> None:
    with pytest.raises(ValidationError):
        DRAFT.validate_python(
            {"title": "X", "split_mode": "equal", "amount": raw, "participants": [1]}
        )
    with pytest.raises(ValidationError):
        SettlementCreate(receiver_id=1, amount=raw, client_request_id=uuid4())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100.00", "100 ₽"),
        ("100.50", "100,50 ₽"),
        ("1250.75", "1 250,75 ₽"),
        ("0.01", "0,01 ₽"),
        ("-1250.01", "−1 250,01 ₽"),
        ("0.00", "0 ₽"),
    ],
)
def test_display_hides_only_zero_kopecks(raw: str, expected: str) -> None:
    assert money(raw) == expected


def test_grid_keeps_priorities_danger_navigation_and_callback_indices() -> None:
    actions = [
        ("Добавить расход", "ex:new:1"),
        ("Кто кому должен", "st:balances:1"),
        ("Расходы", "ex:list:1:0"),
        ("Участники", "members:1:0"),
        ("Пригласить", "invites:1:0"),
        ("История", "st:list:1:all:all:0"),
        ("Удалить", "ex:delete:1"),
        ("Назад", "ex:review"),
        ("Отмена", "ex:cancel"),
    ]
    for colors in (True, False):
        rows = action_keyboard("n", actions, colors=colors).inline_keyboard
        assert [len(row) for row in rows] == [1, 1, 2, 2, 1, 2]
        assert [b.callback_data for row in rows for b in row] == [
            f"l3:n:{i}" for i in range(len(actions))
        ]
        assert all(
            len(row) == 1 for row in rows if any(b.style == "danger" for b in row)
        )


def test_long_labels_people_and_choices_get_full_width() -> None:
    actions = [
        ("Иван Александрович · А", "ex:toggle:1"),
        ("Иван Александрович · Б", "ex:toggle:2"),
        ("Саша", "st:receiver:3"),
        ("Саша · Б", "st:receiver:4"),
        ("Очень длинное вспомогательное действие", "help"),
        ("Профиль", "profile"),
        ("Подтвердить расход", "ex:save"),
        ("Отмена", "ex:cancel"),
    ]
    rows = action_keyboard("n", actions).inline_keyboard
    assert all(len(row) == 1 for row in rows)
    assert "Иван Александрович · А" in rows[0][0].text
    assert not compact("Очень длинное вспомогательное действие")


@pytest.mark.anyio
async def test_equal_and_edit_inputs_preserve_preview_and_retry_intent(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple(amount="100,00")
    assert (await load(j.ui.state)).amount == "100.00"
    await j.choose("Проверить доли")
    preview = j.calls("POST", "/internal/groups/100/expenses/preview")[-1]
    assert json.loads(preview.content)["amount"] == "100.00"
    j.server.fail_after = "POST"
    stale = await j.choose("Подтвердить расход")
    await j.ui.click(stale)
    await j.choose("Повторить исходный запрос")
    posts = j.calls("POST", "/internal/groups/100/expenses")
    assert len(posts) == 2 and posts[0].content == posts[1].content
    assert len(j.server.saved) == 1
    await j.choose("Редактировать")
    await j.choose("Продолжить редактирование")
    await j.choose("Изменить сумму")
    await j.ui.send("100.5")
    assert (await load(j.ui.state)).amount == "100.50"
    await j.choose("Проверить доли")
    assert (
        json.loads(
            j.calls("POST", "/internal/groups/100/expenses/preview")[-1].content
        )["amount"]
        == "100.50"
    )


@pytest.mark.anyio
async def test_custom_zero_and_receipt_input_use_same_parser(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.start("custom")
    await j.ui.send("Такси")
    await j.ui.send("100")
    await j.choose("Выбрать всех")
    await j.choose("Готово")
    for raw in ("0,00", "33,3", "66.70"):
        await j.ui.send(raw)
    draft = await load(j.ui.state)
    assert draft.shares == {"10": "0.00", "20": "33.30", "30": "66.70"}
    assert draft.business().model_dump()["amount"] == "100.00"
    await j.ui.send("/cancel")
    await j.start("by_items")
    await j.ui.send("Чек")
    await j.ui.send("Сок")
    await j.ui.send("0,01")
    await j.choose("Выбрать всех")
    sends = sum(
        isinstance(c.args[1], SendMessage) for c in j.ui.session.await_args_list
    )
    await j.choose("@ex:toggle:30")
    assert (
        sum(isinstance(c.args[1], SendMessage) for c in j.ui.session.await_args_list)
        == sends
    )
    await j.choose("Готово")
    assert (await load(j.ui.state)).business().model_dump()["items"][0][
        "amount"
    ] == "0.01"


@pytest.mark.anyio
async def test_transfer_normalizes_before_freeze(
    settlement_journey: SettlementJourney,
) -> None:
    j = settlement_journey
    await j.draft("100,5")
    j.server.fail_after = "create"
    await j.choose("Да, я уже перевёл деньги")
    await j.choose("Повторить исходную заявку")
    posts = j.calls("POST", "/internal/groups/10/settlements")
    assert len(posts) == 2 and posts[0].content == posts[1].content
    assert json.loads(posts[0].content)["amount"] == "100.50"
    assert len(j.server.saved) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("owner", [True, False])
async def test_group_grid_preserves_owner_permissions(
    journey: Journey, owner: bool
) -> None:
    j = journey
    j.server.profile = j.server.user()
    group = j.server.group()
    if not owner:
        j.server.profile["id"] = 2
    j.server.groups = [group]
    await j.ui.send("/start")
    await j.ui.click("menu:groups")
    await j.choose("Группа 1")
    markup = j.ui.sent[-1].reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    rows = markup.inline_keyboard
    callbacks = [a for a in j.ui.last_actions if a.startswith("invites:")]
    assert bool(callbacks) == owner
    assert [len(row) for row in rows][:4] == [1, 1, 2, 2]
