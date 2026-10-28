"""L-03 user journeys, real Dispatcher + HTTP client, both transports mocked."""

import json
import logging
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe
from aiogram.types import InlineKeyboardMarkup, Update, User
from pydantic import SecretStr

from bot.api_client import ApiClient
from bot.handlers import ACTIVE, UNKNOWN
from bot.main import create_dispatcher
from bot.states import GroupFlow, Navigation, Onboarding
from tests.unit.test_bot_handlers import Harness


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def error(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "error": {
                "code": code,
                "message": "untrusted diagnostic",
                "request_id": "test-request",
            }
        },
    )


@dataclass
class ContractFixture:
    profile: dict[str, object] | None = None
    groups: list[dict[str, object]] = field(default_factory=list)
    invites: list[dict[str, object]] = field(default_factory=list)
    overrides: dict[tuple[str, str], list[httpx.Response | Exception]] = field(
        default_factory=dict
    )
    requests: list[httpx.Request] = field(default_factory=list)
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    issued_token: str | None = None
    owner: int = 1

    def user(self) -> dict[str, object]:
        return {
            "id": self.owner,
            "email": None,
            "telegram_id": 123,
            "created_at": "2026-10-27T00:00:00Z",
        }

    def group(self, group_id: int = 1) -> dict[str, object]:
        return {
            "id": group_id,
            "name": f"Группа {group_id}",
            "owner_id": 1,
            "created_at": "2026-10-27T00:00:00Z",
        }

    def invite(self, key: str) -> dict[str, object]:
        return {
            "id": 1,
            "group_id": 1,
            "client_request_id": key,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "consumed_at": None,
            "revoked_at": None,
        }

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["X-Telegram-ID"] == "123"
        assert "authorization" not in request.headers
        assert request.headers["X-Bot-Service-Token"]
        assert self.token not in str(request.url)
        route = request.method, request.url.path
        if self.overrides.get(route):
            result = self.overrides[route].pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        path = request.url.path
        if path == "/internal/users/me":
            return (
                httpx.Response(200, json=self.profile)
                if self.profile
                else error(404, "telegram_profile_not_found")
            )
        body = json.loads(request.content) if request.content else {}
        if path == "/internal/users/bootstrap":
            assert body == {}
            self.profile = self.user()
            return httpx.Response(200, json=self.profile)
        if path == "/internal/users/telegram-link":
            assert body == {"code": self.token}
            self.profile = {**self.user(), "email": "lera@example.com"}
            return httpx.Response(200, json=self.profile)
        if path == "/internal/groups" and request.method == "POST":
            assert set(body) == {"name", "client_request_id"}
            value = {**self.group(), "name": body["name"]}
            self.groups = [value]
            return httpx.Response(201, json=value)
        if path == "/internal/group-invites/join":
            assert body == {"token": self.token}
            self.groups = [self.group()]
            return httpx.Response(200, json=self.group())
        if path == "/internal/groups/1/invites" and request.method == "POST":
            invite = self.invite(body["client_request_id"])
            self.invites = [invite]
            return httpx.Response(201, json={**invite, "token": self.issued_token})
        if path == "/internal/groups/1/invites/1" and request.method == "DELETE":
            value = {**self.invites[0], "revoked_at": datetime.now(UTC).isoformat()}
            self.invites = [value]
            return httpx.Response(200, json=value)
        if path == "/internal/groups/1":
            return httpx.Response(200, json=self.groups[0])
        items: list[dict[str, object]]
        if path == "/internal/groups":
            items = self.groups
        elif path == "/internal/groups/1/members":
            items = [
                {"user_id": 1, "joined_at": "2026-10-27T00:00:00Z", "is_owner": True}
            ]
        elif path == "/internal/groups/1/invites":
            items = self.invites
        else:
            raise AssertionError("Unexpected method/path")
        offset = int(request.url.params.get("offset", "0"))
        assert request.url.params["limit"] == "20"
        return httpx.Response(
            200,
            json={"items": items[offset : offset + 20], "limit": 20, "offset": offset},
        )


@dataclass
class Journey:
    ui: Harness
    server: ContractFixture

    def button(self, label: str) -> str:
        markup = self.ui.sent[-1].reply_markup
        assert isinstance(markup, InlineKeyboardMarkup)
        matches = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.text == label
        ]
        assert len(matches) == 1 and matches[0] is not None
        return matches[0]

    async def choose(self, label: str) -> None:
        await self.ui.click(self.button(label))

    @property
    def text(self) -> str:
        return "\n".join(message.text for message in self.ui.sent)

    def writes(self, path: str) -> list[httpx.Request]:
        return [
            r for r in self.server.requests if r.url.path == path and r.method != "GET"
        ]

    async def open_group(self) -> None:
        self.server.profile = self.server.user()
        self.server.groups = [self.server.group()]
        await self.ui.click("menu:groups")
        await self.choose("Группа 1 · #1")

    async def invite_confirmation(self) -> None:
        await self.open_group()
        await self.choose("Приглашения")
        await self.choose("Создать приглашение")


@pytest.fixture
async def journey() -> AsyncIterator[Journey]:
    generated = f"{secrets.randbelow(10**8) + 1}:{secrets.token_urlsafe(32)}"
    session = AsyncMock(spec=BaseSession)

    async def telegram_response(bot: Bot, method: Any, **kwargs: Any) -> Any:
        if isinstance(method, GetMe):
            return User(
                id=bot.id, is_bot=True, first_name="Тест", username="skinulis_test_bot"
            )
        return True

    session.side_effect = telegram_response
    telegram = Bot(token=generated, session=session)
    dispatcher = create_dispatcher()
    server = ContractFixture()
    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(server.respond),
    ) as api:
        ui = Harness(telegram, dispatcher, session, api, server.requests)
        try:
            yield Journey(ui, server)
        finally:
            await dispatcher.fsm.close()
            await telegram.session.close()


@pytest.mark.anyio
async def test_new_user_requires_consent_and_stale_double_click_cannot_write(
    journey: Journey,
) -> None:
    ui = journey.ui
    await ui.send("/start")
    assert not journey.writes("/internal/users/bootstrap")
    await journey.choose("Создать профиль")
    assert not journey.writes("/internal/users/bootstrap")
    confirm = journey.button("Да, создать")
    await ui.click(confirm)
    await ui.click(confirm)
    assert len(journey.writes("/internal/users/bootstrap")) == 1
    assert await ui.state.get_state() == Navigation.menu.state
    assert ui.sent[-1].text == UNKNOWN


@pytest.mark.anyio
async def test_existing_user_read_only_and_decline_no_write(journey: Journey) -> None:
    await journey.ui.send("/start")
    await journey.choose("Не сейчас")
    assert all(r.method == "GET" for r in journey.server.requests)
    assert await journey.ui.state.get_data() == {}
    journey.server.profile = journey.server.user()
    for _ in range(2):
        await journey.ui.send("/start")
        assert journey.ui.sent[-1].text == "Что хотите сделать?"
    assert all(r.method == "GET" for r in journey.server.requests)


@pytest.mark.anyio
async def test_link_success_clears_code_and_profile_screen(
    journey: Journey, caplog: pytest.LogCaptureFixture
) -> None:
    await journey.ui.send("/start")
    await journey.choose("Привязать существующий аккаунт")
    assert "POST /users/me/telegram-link-code" in journey.ui.sent[-1].text
    with caplog.at_level(logging.DEBUG):
        await journey.ui.send(journey.server.token)
    await journey.ui.click("menu:profile")
    assert "Telegram + API" in journey.ui.sent[-1].text
    assert "подтвердил привязку" in journey.text
    assert journey.server.token not in journey.text + caplog.text + repr(
        await journey.ui.state.get_data()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("reason", ["invalid", "used", "expired", "revoked"])
async def test_link_invalid_capability_recovery(journey: Journey, reason: str) -> None:
    journey.server.overrides[("POST", "/internal/users/telegram-link")] = [
        error(404, "link_code_invalid")
    ]
    await journey.ui.send("/start")
    await journey.choose("Привязать существующий аккаунт")
    await journey.ui.send(journey.server.token)
    assert "Код недействителен" in journey.ui.sent[-1].text
    assert await journey.ui.state.get_state() == Onboarding.link_code.state
    assert (
        journey.server.token
        not in repr(await journey.ui.state.get_data()) + journey.text
    )
    assert "подтвердил привязку" not in journey.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code",
    ["telegram_identity_conflict", "telegram_already_linked", "email_profile_required"],
)
async def test_link_conflict_never_merges_or_reports_success(
    journey: Journey, code: str
) -> None:
    journey.server.overrides[("POST", "/internal/users/telegram-link")] = [
        error(409, code)
    ]
    await journey.ui.send("/start")
    await journey.choose("Привязать существующий аккаунт")
    await journey.ui.send(journey.server.token)
    assert await journey.ui.state.get_state() == Onboarding.uncertain.state
    assert "подтвердил привязку" not in journey.text
    await journey.choose("Проверить профиль")
    assert len(journey.writes("/internal/users/telegram-link")) == 1


@pytest.mark.anyio
async def test_group_create_normalization_and_same_uuid_retry(journey: Journey) -> None:
    journey.server.profile = journey.server.user()
    journey.server.overrides[("POST", "/internal/groups")] = [
        httpx.ReadTimeout("private diagnostic")
    ]
    await journey.ui.click("menu:create")
    await journey.ui.send("  Cafe\u0301  ")
    await journey.choose("Создать")
    assert "Результат пока неизвестен" in journey.text
    await journey.choose("Повторить тот же запрос")
    writes = journey.writes("/internal/groups")
    assert len(writes) == 2 and writes[0].content == writes[1].content
    assert json.loads(writes[0].content)["name"] == "Café"
    assert "Группа: Café" in journey.ui.sent[-1].text
    assert "Владелец: участник #1" in journey.ui.sent[-1].text


@pytest.mark.anyio
async def test_empty_groups_pagination_and_members(journey: Journey) -> None:
    journey.server.profile = journey.server.user()
    await journey.ui.click("menu:groups")
    assert "пока нет групп" in journey.text
    journey.server.groups = [journey.server.group(i) for i in range(1, 21)]
    await journey.choose("Обновить")
    await journey.choose("Далее")
    assert "На этой странице групп нет" in journey.ui.sent[-1].text
    assert journey.server.requests[-1].url.params["offset"] == "20"
    await journey.choose("Назад по списку")
    await journey.choose("Группа 1 · #1")
    await journey.choose("Все участники")
    assert "#1 — владелец" in journey.ui.sent[-1].text
    await journey.choose("К группе")
    assert "Группа: Группа 1" in journey.ui.sent[-1].text


@pytest.mark.anyio
async def test_invite_issue_list_revoke_and_double_click(journey: Journey) -> None:
    journey.server.issued_token = journey.server.token
    await journey.invite_confirmation()
    confirm = journey.button("Создать приглашение")
    await journey.ui.click(confirm)
    await journey.ui.click(confirm)
    assert len(journey.writes("/internal/groups/1/invites")) == 1
    assert (
        f"https://t.me/skinulis_test_bot?start=i_{journey.server.token}" in journey.text
    )
    assert journey.server.token not in repr(await journey.ui.state.get_data())
    await journey.ui.click("menu:groups")
    await journey.choose("Группа 1 · #1")
    await journey.choose("Приглашения")
    await journey.choose("Отозвать #1")
    confirm = journey.button("Да, отозвать")
    await journey.ui.click(confirm)
    await journey.ui.click(confirm)
    assert len(journey.writes("/internal/groups/1/invites/1")) == 1
    assert "подтвердил отзыв" in journey.text


@pytest.mark.anyio
async def test_invite_replay_null_never_restores_secret_or_issues_another(
    journey: Journey,
) -> None:
    await journey.invite_confirmation()
    await journey.choose("Создать приглашение")
    assert "секрет уже выдавался" in journey.text
    assert "https://t.me" not in journey.text
    assert len(journey.writes("/internal/groups/1/invites")) == 1


@pytest.mark.anyio
async def test_invite_timeout_reads_metadata_then_explicit_revoke(
    journey: Journey,
) -> None:
    await journey.invite_confirmation()
    data = await journey.ui.state.get_data()
    journey.server.invites = [journey.server.invite(data["request_key"])]
    journey.server.overrides[("POST", "/internal/groups/1/invites")] = [
        httpx.ReadTimeout("secret")
    ]
    await journey.choose("Создать приглашение")
    assert "Секрет потерян" in journey.ui.sent[-1].text
    assert "https://t.me" not in journey.text
    await journey.choose("Отозвать потерянное приглашение")
    await journey.choose("Да, отозвать")
    assert len(journey.writes("/internal/groups/1/invites")) == 1
    assert len(journey.writes("/internal/groups/1/invites/1")) == 1


@pytest.mark.anyio
async def test_deep_link_onboarding_then_voluntary_join_and_repeat_update(
    journey: Journey,
) -> None:
    await journey.ui.send("/start i_" + journey.server.token)
    assert "Группа 1" not in journey.text
    assert not journey.writes("/internal/group-invites/join")
    await journey.choose("Создать профиль")
    await journey.choose("Да, создать")
    confirm = journey.button("Вступить")
    assert "Группа 1" not in journey.text
    await journey.ui.click(confirm)
    # Redelivery of the exact Telegram update AND a second callback.
    update = journey.ui.dispatcher.feed_update  # public API used with same id below
    repeated = Update(
        update_id=journey.ui.update_id,
        message=journey.ui.message("/start i_" + journey.server.token),
    )
    await update(journey.ui.bot, repeated, api=journey.ui.api)
    await journey.ui.click(confirm)
    assert len(journey.writes("/internal/group-invites/join")) == 1
    assert "подтвердил: вы вступили" in journey.text
    assert journey.server.token not in journey.text + repr(
        await journey.ui.state.get_data()
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code,status",
    [("invite_invalid", 404), ("already_member", 409), ("group_full", 409)],
)
async def test_join_safe_errors_and_no_group_disclosure(
    journey: Journey, code: str, status: int
) -> None:
    journey.server.profile = journey.server.user()
    journey.server.overrides[("POST", "/internal/group-invites/join")] = [
        error(status, code)
    ]
    await journey.ui.send("/start i_" + journey.server.token)
    await journey.choose("Вступить")
    assert "подтвердил: вы вступили" not in journey.text
    assert "Группа 1" not in journey.text
    assert not any("members" in r.url.path for r in journey.server.requests)
    assert journey.server.token not in journey.text + repr(
        await journey.ui.state.get_data()
    )


@pytest.mark.anyio
async def test_join_timeout_reads_groups_without_blind_post_retry(
    journey: Journey,
) -> None:
    journey.server.profile = journey.server.user()
    journey.server.overrides[("POST", "/internal/group-invites/join")] = [
        httpx.ReadTimeout("secret")
    ]
    await journey.ui.send("/start i_" + journey.server.token)
    confirm = journey.button("Вступить")
    await journey.ui.click(confirm)
    await journey.choose("Обновить")
    await journey.ui.click(confirm)
    assert "Результат пока неизвестен" in journey.text
    assert "подтвердил: вы вступили" not in journey.text
    assert len(journey.writes("/internal/group-invites/join")) == 1
    assert any(r.url.path == "/internal/groups" for r in journey.server.requests)


@pytest.mark.anyio
async def test_member_cannot_see_owner_action_and_api_rechecks_stale_owner(
    journey: Journey,
) -> None:
    await journey.open_group()
    owner_button = journey.button("Приглашения")
    journey.server.overrides[("GET", "/internal/groups/1/invites")] = [
        error(403, "owner_required")
    ]
    await journey.ui.click(owner_button)
    assert "только владелец" in journey.ui.sent[-1].text
    assert not journey.writes("/internal/groups/1/invites")
    journey.server.owner = 2
    journey.server.profile = journey.server.user()
    await journey.ui.click("menu:groups")
    await journey.choose("Группа 1 · #1")
    markup = journey.ui.sent[-1].reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    assert "Приглашения" not in [b.text for row in markup.inline_keyboard for b in row]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "stage", ["consent", "link", "name", "confirm", "join", "invite", "revoke"]
)
async def test_cancel_each_step_and_repeated_start_preserve_draft(
    journey: Journey, stage: str
) -> None:
    if stage in {"consent", "link"}:
        await journey.ui.send("/start")
        await journey.choose(
            "Создать профиль"
            if stage == "consent"
            else "Привязать существующий аккаунт"
        )
    elif stage == "join":
        journey.server.profile = journey.server.user()
        await journey.ui.send("/start i_" + journey.server.token)
    elif stage in {"name", "confirm"}:
        journey.server.profile = journey.server.user()
        await journey.ui.click("menu:create")
        if stage == "confirm":
            await journey.ui.send("Поездка")
    else:
        await journey.invite_confirmation()
        if stage == "revoke":
            await journey.choose("Создать приглашение")
            await journey.choose("Отозвать #1")
    before = await journey.ui.state.get_data()
    await journey.ui.send("/start")
    assert journey.ui.sent[-1].text == ACTIVE
    assert await journey.ui.state.get_data() == before
    writes_before = sum(r.method != "GET" for r in journey.server.requests)
    await journey.ui.send("/cancel")
    assert sum(r.method != "GET" for r in journey.server.requests) == writes_before
    after = await journey.ui.state.get_data()
    assert (
        not {"draft", "invite", "request_key", "group_id", "invite_id"} & after.keys()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500, 503])
async def test_start_error_is_not_absent_profile_or_success(
    journey: Journey, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    private = journey.server.token
    journey.server.overrides[("GET", "/internal/users/me")] = [
        httpx.Response(
            status,
            json={
                "error": {
                    "code": private,
                    "message": "Traceback " + private,
                    "request_id": private,
                }
            },
        )
    ]
    with caplog.at_level(logging.DEBUG):
        await journey.ui.send("/start")
    assert await journey.ui.state.get_state() == Onboarding.uncertain.state
    assert "Создать Telegram-only профиль или" not in journey.text
    assert private not in journey.text + caplog.text
    assert all(r.method == "GET" for r in journey.server.requests)


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["bootstrap", "telegram-link"])
async def test_identity_timeout_reads_profile_without_false_success(
    journey: Journey, operation: str
) -> None:
    journey.server.overrides[("POST", "/internal/users/" + operation)] = [
        httpx.ReadTimeout("secret")
    ]
    await journey.ui.send("/start")
    if operation == "bootstrap":
        await journey.choose("Создать профиль")
        await journey.choose("Да, создать")
    else:
        await journey.choose("Привязать существующий аккаунт")
        await journey.ui.send(journey.server.token)
    assert "Результат пока неизвестен" in journey.text
    assert "API подтвердил" not in journey.text
    await journey.choose("Проверить профиль")
    assert len(journey.writes("/internal/users/" + operation)) == 1


@pytest.mark.anyio
async def test_bad_name_code_stale_callback_restart_and_unexpected_text(
    journey: Journey,
) -> None:
    await journey.ui.send("/start")
    stale = journey.button("Создать профиль")
    await journey.choose("Привязать существующий аккаунт")
    await journey.ui.send("some password or JWT")
    assert "Нужен только одноразовый код" in journey.ui.sent[-1].text
    await journey.ui.click(stale)
    assert journey.ui.sent[-1].text == UNKNOWN
    await journey.ui.send("/unknown")
    assert "текущем экране" in journey.ui.sent[-1].text
    await journey.ui.state.clear()  # restart loses MemoryStorage draft
    await journey.ui.click(stale)
    assert journey.ui.sent[-1].text == UNKNOWN
    journey.server.profile = journey.server.user()
    await journey.ui.click("menu:create")
    for invalid in [" ", "x" * 121, "a\u200db", "a\x00b"]:
        await journey.ui.send(invalid)
        assert await journey.ui.state.get_state() == GroupFlow.name.state
    assert all(r.method == "GET" for r in journey.server.requests)


@pytest.mark.anyio
async def test_bootstrap_lost_response_but_profile_exists_is_not_false_creation(
    journey: Journey,
) -> None:
    await journey.ui.send("/start")
    await journey.choose("Создать профиль")
    journey.server.profile = journey.server.user()
    journey.server.overrides[("POST", "/internal/users/bootstrap")] = [
        httpx.ReadTimeout("private")
    ]
    await journey.choose("Да, создать")
    assert "Профиль сейчас существует" in journey.text
    assert "API подтвердил профиль" not in journey.text
    assert "Результат пока неизвестен" in journey.text
    assert len(journey.writes("/internal/users/bootstrap")) == 1


@pytest.mark.anyio
async def test_join_decline_discards_capability_without_join(journey: Journey) -> None:
    journey.server.profile = journey.server.user()
    await journey.ui.send("/start i_" + journey.server.token)
    await journey.choose("Не вступать")
    assert not journey.writes("/internal/group-invites/join")
    assert "invite" not in await journey.ui.state.get_data()


@pytest.mark.anyio
async def test_invite_unknown_result_can_read_next_page_after_api_recovery(
    journey: Journey,
) -> None:
    from uuid import uuid4

    await journey.invite_confirmation()
    key = (await journey.ui.state.get_data())["request_key"]
    journey.server.invites = [
        {**journey.server.invite(str(uuid4())), "id": i} for i in range(2, 22)
    ] + [journey.server.invite(key)]
    journey.server.overrides[("POST", "/internal/groups/1/invites")] = [
        httpx.ConnectError("private")
    ]
    journey.server.overrides[("GET", "/internal/groups/1/invites")] = [
        error(503, "internal_error")
    ]
    await journey.choose("Создать приглашение")
    await journey.choose("Проверить metadata")
    assert "остаётся неизвестным" in journey.ui.sent[-1].text
    await journey.choose("Проверить следующую страницу")
    assert "Найдена запись приглашения #1" in journey.ui.sent[-1].text
    assert len(journey.writes("/internal/groups/1/invites")) == 1
    assert "https://t.me" not in journey.text


@pytest.mark.anyio
async def test_revoke_timeout_retries_same_target_and_consumed_conflict(
    journey: Journey,
) -> None:
    await journey.invite_confirmation()
    await journey.choose("Создать приглашение")
    await journey.choose("Отозвать #1")
    journey.server.overrides[("DELETE", "/internal/groups/1/invites/1")] = [
        httpx.ReadTimeout("private"),
        error(409, "invite_consumed"),
    ]
    await journey.choose("Да, отозвать")
    await journey.choose("Повторить отзыв")
    writes = journey.writes("/internal/groups/1/invites/1")
    assert len(writes) == 2
    assert "Приглашение уже использовано" in journey.text
    assert "API подтвердил отзыв" not in journey.text


@pytest.mark.anyio
async def test_join_timeout_and_failed_read_remain_uncertain(journey: Journey) -> None:
    journey.server.profile = journey.server.user()
    journey.server.overrides[("POST", "/internal/group-invites/join")] = [
        httpx.ReadTimeout("private")
    ]
    journey.server.overrides[("GET", "/internal/groups")] = [
        error(503, "internal_error")
    ]
    await journey.ui.send("/start i_" + journey.server.token)
    await journey.choose("Вступить")
    assert "Результат вступления неизвестен" in journey.ui.sent[-1].text
    await journey.choose("Проверить мои группы")
    assert len(journey.writes("/internal/group-invites/join")) == 1


@pytest.mark.anyio
async def test_no_username_prevents_invite_write(
    journey: Journey, monkeypatch: pytest.MonkeyPatch
) -> None:
    await journey.invite_confirmation()
    monkeypatch.setattr(
        journey.ui.bot,
        "get_me",
        AsyncMock(return_value=User(id=1, is_bot=True, first_name="Тест")),
    )
    await journey.choose("Создать приглашение")
    assert "Приглашение не запрашивали" in journey.ui.sent[-1].text
    assert not journey.writes("/internal/groups/1/invites")
