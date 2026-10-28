"""Exact service wire requests and independent DTO/OpenAPI compatibility checks."""

import json
import logging
import secrets
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.main import create_app
from bot.api_client import ApiClient, ApiError, ApiFailure
from bot.config import BotSettings
from bot.dto import (
    GroupDraft,
    GroupProfile,
    InviteIssued,
    InviteProfile,
    MemberProfile,
    Page,
    UserProfile,
)
from bot.middleware import SafeTelegramLogs


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_all_service_requests_use_exact_contract_and_separate_actor_headers() -> (
    None
):
    key = uuid4()
    secret = secrets.token_urlsafe(48)
    capability = secrets.token_urlsafe(32)
    created = "2026-10-27T00:00:00Z"
    user = {"id": 1, "email": None, "telegram_id": 123, "created_at": created}
    group = {"id": 1, "name": "Trip", "owner_id": 1, "created_at": created}
    member = {"user_id": 1, "joined_at": created, "is_owner": True}
    invite = {
        "id": 2,
        "group_id": 1,
        "client_request_id": str(key),
        "created_at": created,
        "expires_at": "2026-10-28T00:00:00Z",
        "revoked_at": None,
        "consumed_at": None,
    }
    expected = [
        ("GET", "/internal/users/me", None, 200, user),
        ("POST", "/internal/users/bootstrap", {}, 200, user),
        ("POST", "/internal/users/telegram-link", {"code": capability}, 200, user),
        (
            "GET",
            "/internal/groups",
            None,
            200,
            {"items": [group], "limit": 20, "offset": 20},
        ),
        (
            "POST",
            "/internal/groups",
            {"name": "Trip", "client_request_id": str(key)},
            201,
            group,
        ),
        ("GET", "/internal/groups/1", None, 200, group),
        (
            "GET",
            "/internal/groups/1/members",
            None,
            200,
            {"items": [member], "limit": 20, "offset": 0},
        ),
        (
            "GET",
            "/internal/groups/1/invites",
            None,
            200,
            {"items": [invite], "limit": 20, "offset": 0},
        ),
        (
            "POST",
            "/internal/groups/1/invites",
            {"client_request_id": str(key)},
            201,
            {**invite, "token": capability},
        ),
        ("DELETE", "/internal/groups/1/invites/2", None, 200, invite),
        ("POST", "/internal/group-invites/join", {"token": capability}, 200, group),
    ]
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        method, path, body, status, response = expected[count]
        count += 1
        assert request.method == method and request.url.path == path
        assert (json.loads(request.content) if request.content else None) == body
        assert request.headers["X-Bot-Service-Token"] == secret
        assert request.headers["X-Telegram-ID"] == "123"
        assert "authorization" not in request.headers
        assert capability not in str(request.url)
        if (
            path.endswith(("members", "invites"))
            and method == "GET"
            or path == "/internal/groups"
            and method == "GET"
        ):
            assert set(request.url.params) == {"limit", "offset"}
        return httpx.Response(status, json=response)

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        assert isinstance(await api.profile(123), UserProfile)
        await api.bootstrap(123)
        await api.link(123, SecretStr(capability))
        assert (await api.groups(123, offset=20)).offset == 20
        await api.create_group(123, GroupDraft(name="Trip", client_request_id=key))
        await api.group(123, 1)
        await api.members(123, 1)
        await api.invites(123, 1)
        result = await api.issue_invite(123, 1, key)
        assert capability not in repr(result)
        await api.revoke_invite(123, 1, 2)
        await api.join(123, SecretStr(capability))
    assert count == len(expected)


def test_client_dto_fields_match_actual_openapi() -> None:
    schema = create_app(
        Settings(_env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(24)))
    ).openapi()
    components = schema["components"]["schemas"]
    for model in (
        UserProfile,
        GroupProfile,
        MemberProfile,
        InviteProfile,
        InviteIssued,
    ):
        assert set(model.model_fields) == set(components[model.__name__]["properties"])
    assert set(Page[GroupProfile].model_fields) == {"items", "limit", "offset"}
    for path in (
        "/internal/users/me",
        "/internal/users/bootstrap",
        "/internal/users/telegram-link",
        "/internal/groups",
        "/internal/groups/{group_id}",
        "/internal/groups/{group_id}/members",
        "/internal/groups/{group_id}/invites",
        "/internal/groups/{group_id}/invites/{invite_id}",
        "/internal/group-invites/join",
    ):
        assert path in schema["paths"]


@pytest.mark.anyio
@pytest.mark.parametrize("actor", [0, -1, 2**63, True])
async def test_invalid_actor_never_sends_request(actor: int) -> None:
    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(
            lambda _: pytest.fail("Must fail before request")
        ),
    ) as api:
        with pytest.raises(ApiError) as caught:
            await api.profile(actor)
        assert caught.value.kind == ApiFailure.INPUT


@pytest.mark.anyio
async def test_service_credential_is_required_and_health_does_not_send_it() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "X-Bot-Service-Token" not in request.headers
        assert "X-Telegram-ID" not in request.headers
        return httpx.Response(200, json={"status": "ok", "database": "ok"})

    async with ApiClient(
        "http://api.test", transport=httpx.MockTransport(respond)
    ) as api:
        with pytest.raises(ApiError) as caught:
            await api.profile(123)
        assert caught.value.kind == ApiFailure.AUTH
        await api.health()
    assert len(requests) == 1


@pytest.mark.parametrize("invalid", ["", "x" * 42, "x" * 129, ":" * 43, "я" * 43])
def test_service_configuration_fails_safely(invalid: str) -> None:
    with pytest.raises(ValidationError) as caught:
        BotSettings(
            _env_file=None,
            telegram_bot_token=SecretStr(
                f"{secrets.randbelow(10**8) + 1}:{secrets.token_urlsafe(32)}"
            ),
            bot_service_token=SecretStr(invalid),
        )
    if invalid:
        assert invalid not in str(caught.value)


def test_library_log_filter_removes_identity_and_exception_details() -> None:
    private = secrets.token_urlsafe(32)
    filtering = SafeTelegramLogs()
    info = logging.LogRecord(
        "aiogram.event", logging.INFO, "", 1, "bot id=%s", (123,), None
    )
    assert not filtering.filter(info)
    warning = logging.LogRecord(
        "aiogram.dispatcher",
        logging.ERROR,
        "",
        1,
        "%s",
        (private,),
        (ValueError, ValueError(private), None),
    )
    assert filtering.filter(warning)
    assert private not in logging.Formatter().format(warning)
    assert warning.exc_info is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        {
            "id": True,
            "email": None,
            "telegram_id": 123,
            "created_at": "2026-10-27T00:00:00Z",
        },
        {
            "id": 1,
            "email": None,
            "telegram_id": "123",
            "created_at": "2026-10-27T00:00:00Z",
        },
        {"id": 1, "email": None, "telegram_id": 123},
    ],
)
async def test_malformed_identity_response_never_becomes_success(
    body: dict[str, object],
) -> None:
    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    ) as api:
        with pytest.raises(ApiError) as caught:
            await api.profile(123)
        assert caught.value.kind == ApiFailure.UNEXPECTED
