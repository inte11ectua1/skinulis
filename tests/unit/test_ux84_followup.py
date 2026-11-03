"""Live-feedback regressions: icon/color semantics, screen lifecycle and guarded menu."""

from typing import Any

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import (
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
    SetChatMenuButton,
    SetMyCommands,
)
from aiogram.types import User

from bot.commands import COMMANDS, configure_test_menu
from bot.expense_wizard import load
from bot.keyboards import action_keyboard
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


def test_semantic_icons_colors_and_plain_fallback() -> None:
    actions = [
        ("Добавить расход", "ex:new:1"),
        ("Пригласить друзей", "invites:1:0"),
        ("Подтвердить расход", "ex:save"),
        ("Удалить", "ex:delete:1"),
        ("Назад", "ex:review"),
        ("Помощь", "help"),
    ]
    buttons = [
        b for row in action_keyboard("nonce", actions).inline_keyboard for b in row
    ]
    assert [b.style for b in buttons] == [
        "primary",
        None,
        "success",
        "danger",
        None,
        None,
    ]
    assert [b.text.split()[0] for b in buttons] == ["➕", "🔗", "✅", "🗑", "↩️", "❓"]
    assert (
        action_keyboard("n", [("Исправить черновик", "ex:review")])
        .inline_keyboard[0][0]
        .text.startswith("✏️ ")
    )
    fallback = [
        b
        for row in action_keyboard("nonce", actions, colors=False).inline_keyboard
        for b in row
    ]
    assert [b.text for b in fallback] == [b.text for b in buttons]
    assert all(b.style is None and b.icon_custom_emoji_id is None for b in fallback)
    assert [b.callback_data for b in fallback] == [b.callback_data for b in buttons]
    for label in ("Главное меню", "← Главное меню"):
        assert (
            action_keyboard("n", [(label, "home")]).inline_keyboard[0][0].text
            == "🏠 Главное меню"
        )


@pytest.mark.anyio
async def test_user_text_retires_previous_keyboard_and_places_new_panel_at_bottom(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.start("equal")
    old = (await j.ui.state.get_data())["panel_id"]
    stale = j.ui.action("ex:cancel")
    start = len(j.ui.session.await_args_list)
    await j.ui.send("Такси")
    methods = [c.args[1] for c in j.ui.session.await_args_list[start:]]
    cleanup = next(
        i
        for i, m in enumerate(methods)
        if isinstance(m, EditMessageReplyMarkup) and m.message_id == old
    )
    send = next(
        i
        for i, m in enumerate(methods)
        if isinstance(m, SendMessage) and m.reply_markup
    )
    assert cleanup < send
    assert (await j.ui.state.get_data())["panel_id"] != old
    assert not any(isinstance(m, EditMessageText) for m in methods)
    await j.ui.click(stale)
    assert j.ui.alerts[-1].show_alert and not j.server.saved
    assert (await load(j.ui.state)).title == "Такси"


@pytest.mark.anyio
async def test_start_has_one_response_per_explicit_command_and_no_competing_menu(
    journey: Journey,
) -> None:
    j = journey
    j.server.profile = j.server.user()
    for _ in range(4):
        before = len(j.ui.sent)
        await j.ui.send("/start")
        assert len(j.ui.sent) == before + 1
        assert (await j.ui.state.get_data())["actions"]
    methods = [c.args[1] for c in j.ui.session.await_args_list]
    assert len([m for m in methods if isinstance(m, EditMessageReplyMarkup)]) == 3
    assert not j.writes("/internal/users/bootstrap")


@pytest.mark.anyio
async def test_commands_and_help_preserve_frozen_intent_but_rotate_old_callbacks(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    await j.choose("Проверить доли")
    previous = (await load(j.ui.state)).model_dump()
    stale = j.ui.action("ex:save")
    for command in ("/groups", "/profile", "/start", "/help"):
        await j.ui.send(command)
        assert (await load(j.ui.state)).model_dump() == previous
    await j.ui.click(stale)
    assert j.ui.alerts[-1].show_alert and not j.server.saved
    await j.choose("Продолжить ввод")
    await j.choose("Подтвердить расход")
    assert len(j.server.saved) == 1
    assert len(j.calls("POST", "/internal/groups/100/expenses")) == 1


@pytest.mark.anyio
async def test_command_menu_routes_are_real(journey: Journey) -> None:
    j = journey
    j.server.profile = j.server.user()
    for cmd, expected in [
        ("/groups", "пока нет групп"),
        ("/profile", "Мой профиль"),
        ("/help", "Как пользоваться"),
        ("/cancel", "Сохранённые записи"),
    ]:
        await j.ui.send(cmd)
        assert expected in j.ui.sent[-1].text
    assert all(r.method == "GET" for r in j.server.requests)


@pytest.mark.anyio
async def test_menu_provisioning_refuses_other_identity_before_writes(
    journey: Journey,
) -> None:
    bot = journey.ui.bot
    before = len(journey.ui.session.await_args_list)
    with pytest.raises(ValueError):
        await configure_test_menu(
            bot,
            User(id=1, is_bot=True, first_name="x", username="skinulis_expenses_bot"),
        )
    assert len(journey.ui.session.await_args_list) == before
    await configure_test_menu(
        bot, User(id=1, is_bot=True, first_name="x", username="skinulis_testing_bot")
    )
    methods = [c.args[1] for c in journey.ui.session.await_args_list[before:]]
    assert [type(m) for m in methods] == [
        SetMyCommands,
        SetMyCommands,
        SetChatMenuButton,
    ]
    assert [c.command for c in COMMANDS] == [
        "start",
        "groups",
        "profile",
        "help",
        "cancel",
    ]
    assert methods[-1].menu_button.type == "commands"


@pytest.mark.anyio
async def test_edit_failure_cleanup_then_fresh_card_and_no_financial_retry(
    journey: Journey,
) -> None:
    j = journey
    message = j.ui.message("x").as_(j.ui.bot)
    await screen(message, j.ui.state, "Карточка", [("Назад", "home")])
    original = j.ui.session.side_effect

    async def unavailable(bot: Bot, method: Any, **kw: Any) -> Any:
        if isinstance(method, EditMessageText):
            raise TelegramBadRequest(method=method, message="message can't be edited")
        return await original(bot, method, **kw)

    j.ui.session.side_effect = unavailable
    before = len(j.ui.session.await_args_list)
    await screen(message, j.ui.state, "Новая", [("Назад", "home")])
    methods = [c.args[1] for c in j.ui.session.await_args_list[before:]]
    assert [type(m) for m in methods] == [
        EditMessageText,
        EditMessageReplyMarkup,
        SendMessage,
    ]

    async def offline(bot: Bot, method: Any, **kw: Any) -> Any:
        if isinstance(method, (EditMessageText, EditMessageReplyMarkup)):
            raise TelegramNetworkError(method=method, message="network")
        return await original(bot, method, **kw)

    j.ui.session.side_effect = offline
    before = len(j.ui.sent)
    with pytest.raises(TelegramNetworkError):
        await screen(message, j.ui.state, "Сбой", [("Назад", "home")])
    assert len(j.ui.sent) == before + 1  # failed edit attempt, no competing send
    assert (await j.ui.state.get_data())["screen"] is None
    assert not j.writes("/internal/groups")


@pytest.mark.anyio
async def test_restart_retires_clicked_historical_keyboard_not_current_panel(
    journey: Journey,
) -> None:
    from bot.main import create_dispatcher

    j = journey
    j.server.profile = j.server.user()
    await j.ui.send("/start")
    old_panel = (await j.ui.state.get_data())["panel_id"]
    stale = j.ui.action("create")
    await j.ui.dispatcher.fsm.close()
    j.ui.dispatcher = create_dispatcher()
    await j.ui.send("/start")
    current_panel = (await j.ui.state.get_data())["panel_id"]
    before = len(j.ui.session.await_args_list)
    await j.ui.click(
        stale, message=j.ui.message("old").model_copy(update={"message_id": old_panel})
    )
    cleanups = [
        c.args[1]
        for c in j.ui.session.await_args_list[before:]
        if isinstance(c.args[1], EditMessageReplyMarkup)
    ]
    assert [m.message_id for m in cleanups] == [old_panel]
    assert (
        current_panel != old_panel
        and (await j.ui.state.get_data())["panel_id"] == current_panel
    )
    assert j.ui.alerts[-1].show_alert and not j.writes("/internal/groups")


@pytest.mark.anyio
async def test_repeated_blocked_navigation_does_not_accumulate_notice_text(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.simple()
    for _ in range(3):
        await j.ui.send("/groups")
        assert j.ui.sent[-1].text.count("Есть незавершённый ввод") == 1
    assert not j.server.saved


@pytest.mark.anyio
async def test_input_from_help_does_not_keep_stale_return_screen(
    expense_journey: ExpenseJourney,
) -> None:
    j = expense_journey
    await j.start("equal")
    await j.ui.send("/help")
    await j.ui.send("Такси")
    assert (await load(j.ui.state)).title == "Такси"
    assert not (await j.ui.state.get_data()).get("resume_view")
    await j.ui.send("/help")
    await j.choose("Продолжить ввод")
    assert "Общая сумма" in j.ui.sent[-1].text
    assert not j.server.saved
