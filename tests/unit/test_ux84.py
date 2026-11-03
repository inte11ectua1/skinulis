"""Rendered product behavior, not a green-CI substitute for human visual acceptance."""

from datetime import UTC, datetime

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import EditMessageText, SendMessage
from pydantic import ValidationError

from app.schemas.auth import BootstrapInput, ProfileUpdate
from bot.dto import MemberProfile
from bot.expense_wizard import load
from bot.presentation import html_card, member_names, money
from bot.ui import screen
from tests.unit import test_bot_expenses as expense_tests
from tests.unit import test_bot_onboarding_groups as onboarding_tests
from tests.unit.test_bot_expenses import ExpenseJourney
from tests.unit.test_bot_onboarding_groups import Journey

expense_journey = expense_tests.expense_journey
journey = onboarding_tests.journey


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize(
    "raw", ["", "  ", "x" * 65, "name\nname", "hidden\u200b", "bad\u202e", "join\u200d"]
)
def test_display_name_rejects_controls_empty_and_long(raw: str) -> None:
    with pytest.raises(ValidationError):
        ProfileUpdate(display_name=raw)
    with pytest.raises(ValidationError):
        BootstrapInput(display_name=raw)


def test_names_are_not_credentials_and_normalize_without_stripping_markup() -> None:
    assert ProfileUpdate(display_name="  Е\u0308лка <b>  ").display_name == "Ёлка <b>"
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate({"display_name": "Маша", "user_id": 123})
    assert BootstrapInput().display_name is None


def test_duplicate_names_are_selectable_without_public_ids() -> None:
    rows = [
        MemberProfile(
            user_id=u,
            display_name="Саша",
            joined_at=datetime(2026, 11, 3, tzinfo=UTC),
            is_owner=u == 9001,
        )
        for u in (9001, 9922)
    ]
    # Wire strict DTO parses real JSON datetime, not arbitrary Python strings.
    rows = [MemberProfile.model_validate_json(r.model_dump_json()) for r in rows]
    names = member_names(rows)
    assert names == {9001: "Саша · А", 9922: "Саша · Б"}
    assert "9001" not in str(names.values()) and "9922" not in str(names.values())


def test_html_and_money_only_present_server_values() -> None:
    assert (
        html_card("Ужин <script>\nАня & Боря")
        == "<b>Ужин &lt;script&gt;</b>\nАня &amp; Боря"
    )
    assert money("3200.00") == "3 200 ₽"
    assert money("-33.34") == "−33,34 ₽"
    assert money("0.00") == "0 ₽"


@pytest.mark.anyio
async def test_multi_select_is_one_message_and_all_none_are_real_choices(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.start("equal")
    await j.ui.send("Тест <b>")
    await j.ui.send("100.00")
    initial_sends = sum(
        isinstance(c.args[1], SendMessage) for c in j.ui.session.await_args_list
    )
    stale = j.ui.action("ex:all")
    await j.choose("Выбрать всех")
    assert len((await load(j.ui.state)).selected) == 3
    assert "Выбрано: 3 из 3" in j.ui.sent[-1].text
    await j.choose("Снять выбор")
    assert not (await load(j.ui.state)).selected
    await j.choose("Готово")
    assert "Выбрано: 0 из 3" in j.ui.sent[-1].text
    await j.ui.click(stale)
    assert not (await load(j.ui.state)).selected
    assert (
        sum(isinstance(c.args[1], SendMessage) for c in j.ui.session.await_args_list)
        == initial_sends
    )
    assert any(
        isinstance(c.args[1], EditMessageText) for c in j.ui.session.await_args_list
    )
    assert not j.calls("POST", "/internal/groups/100/expenses")


@pytest.mark.anyio
async def test_card_escapes_user_content_and_has_no_system_identity(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Проверить доли")
    text = j.ui.sent[-1].text
    assert "Поровну" in text and "33,34 ₽" in text
    assert all(
        v not in text
        for v in ("#10", "#20", "#30", "UUID", "(API)", "equal", "custom", "by_items")
    )
    assert j.ui.sent[-1].parse_mode == "HTML"


@pytest.mark.anyio
async def test_edit_missing_falls_back_once_but_network_error_is_not_financial_retry(
    journey: Journey,
) -> None:
    ui = journey.ui
    await screen(
        ui.message("x").as_(ui.bot),
        ui.state,
        "Первая\n<b>ввод</b>",
        [("Назад", "home")],
    )
    before = len(ui.sent)
    original = ui.session.side_effect

    async def missing(bot: object, method: object, **kw: object) -> object:
        if isinstance(method, EditMessageText):
            raise TelegramBadRequest(method=method, message="message to edit not found")
        return await original(bot, method, **kw)

    ui.session.side_effect = missing
    await screen(ui.message("x").as_(ui.bot), ui.state, "Вторая", [("Назад", "home")])
    assert len(ui.sent) == before + 2  # Failed edit attempt + one fallback send.

    async def offline(bot: object, method: object, **kw: object) -> object:
        if isinstance(method, EditMessageText):
            raise TelegramNetworkError(method=method, message="network")
        return await original(bot, method, **kw)

    ui.session.side_effect = offline
    with pytest.raises(TelegramNetworkError):
        await screen(
            ui.message("x").as_(ui.bot), ui.state, "Третья", [("Назад", "home")]
        )
    assert not journey.writes("/internal/groups")


@pytest.mark.anyio
async def test_profile_can_rename_and_old_account_never_autowrites(
    journey: Journey,
) -> None:
    j = journey
    j.server.profile = {**j.server.user(), "display_name": "Старое имя"}
    await j.ui.send("/start")
    assert all(r.method == "GET" for r in j.server.requests)
    await j.ui.click("menu:profile")
    await j.choose("Изменить имя")
    await j.ui.send("  Анна <b>& друзья  ")
    assert j.server.profile["display_name"] == "Анна <b>& друзья"
    assert "Анна &lt;b&gt;&amp; друзья" in j.ui.sent[-1].text
    assert "#1" not in j.ui.sent[-1].text
    assert len([r for r in j.server.requests if r.method == "PATCH"]) == 1
    await j.ui.send("/start")
    assert j.server.profile["display_name"] == "Анна <b>& друзья"


@pytest.mark.anyio
async def test_bootstrap_uses_telegram_name_only_after_consent_without_username(
    journey: Journey,
) -> None:
    j = journey
    await j.ui.send("/start")
    assert not j.writes("/internal/users/bootstrap")
    await j.choose("Создать профиль")
    assert not j.writes("/internal/users/bootstrap")
    await j.choose("Да, создать")
    assert j.server.profile is not None and j.server.profile["display_name"] == "Тест"


@pytest.mark.anyio
async def test_duplicate_human_buttons_select_different_internal_people(
    expense_journey: ExpenseJourney,
) -> None:
    import httpx

    j = expense_journey
    response = httpx.Response(
        200,
        json={
            "items": [
                {
                    "user_id": u,
                    "display_name": "Саша" if u in (10, 20) else "Лера",
                    "joined_at": "2026-11-03T00:00:00Z",
                    "is_owner": u == 10,
                }
                for u in (10, 20, 30)
            ],
            "limit": 20,
            "offset": 0,
        },
    )
    j.server.overrides["GET", "/internal/groups/100/members"] = [response] * 8
    await j.start("equal")
    await j.ui.send("Кофе")
    await j.ui.send("100.00")
    labels = str(j.ui.sent[-1].reply_markup)
    assert "Саша · А" in labels and "Саша · Б" in labels and "#20" not in labels
    await j.choose("@ex:toggle:20")
    assert (await load(j.ui.state)).selected == [20]


def test_generated_alias_cannot_collide_with_typed_name_or_long_prefix() -> None:
    def people(values: list[str]) -> list[MemberProfile]:
        return [
            MemberProfile(
                user_id=i + 1,
                display_name=v,
                joined_at=datetime(2026, 11, 3, tzinfo=UTC),
                is_owner=i == 0,
            )
            for i, v in enumerate(values)
        ]

    for values in [
        ["Саша", "Саша", "Саша · А"],
        ["Длинное имя" * 5 + "А", "Длинное имя" * 5 + "Б"],
    ]:
        names = member_names(people(values))
        assert len(set(names.values())) == len(values)
        assert all(len(v) < 55 for v in names.values())
