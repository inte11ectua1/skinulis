"""Approved GET/DELETE HTTP contract, serialization and authentication boundaries."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ApiError
from app.core.identity_tokens import new_secret, secret_digest
from app.core.security import create_access_token
from app.db import get_session
from app.main import create_app
from app.models import GroupInvite, User
from app.services import groups

FIELDS = {
    "id",
    "group_id",
    "client_request_id",
    "created_at",
    "expires_at",
    "consumed_at",
    "revoked_at",
}


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, postgres_password=SecretStr(new_secret()))


@pytest.fixture
def session() -> MagicMock:
    value = MagicMock(spec=Session)
    user = User(id=7, telegram_id=123)
    value.get.return_value = user
    value.scalar.return_value = user
    return value


@pytest.fixture
def client(settings: Settings, session: MagicMock) -> Iterator[TestClient]:
    application = create_app(settings)
    application.dependency_overrides[get_session] = lambda: session
    with TestClient(application) as instance:
        yield instance


def auth(settings: Settings, internal: bool) -> tuple[str, dict[str, str]]:
    if internal:
        return "/internal", {
            "X-Bot-Service-Token": settings.require_bot_service_token(),
            "X-Telegram-ID": "123",
        }
    return "", {
        "Authorization": "Bearer "
        + create_access_token(7, settings.require_jwt_secret(), 15)
    }


def record() -> GroupInvite:
    now = datetime(2026, 10, 27, tzinfo=UTC)
    return GroupInvite(
        id=2,
        group_id=1,
        client_request_id=uuid4(),
        token_hash=secret_digest(new_secret()),
        created_at=now,
        expires_at=now + timedelta(hours=24),
        consumed_by=8,
        consumed_at=now + timedelta(minutes=1),
        revoked_at=None,
    )


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_metadata_page_uses_actor_and_never_serializes_secrets(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    internal: bool,
    empty: bool,
) -> None:
    prefix, headers = auth(settings, internal)
    stored = record()
    service = Mock(return_value=[] if empty else [stored])
    monkeypatch.setattr(groups, "list_invites", service)
    response = client.get(
        prefix + "/groups/1/invites?limit=1&offset=2", headers=headers
    )
    assert (
        response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    )
    body = response.json()
    assert set(body) == {"items", "limit", "offset"}
    assert (body["limit"], body["offset"]) == (1, 2)
    if empty:
        assert body["items"] == []
    else:
        assert set(body["items"][0]) == FIELDS
        assert body["items"][0]["client_request_id"] == str(stored.client_request_id)
        assert stored.token_hash not in response.text
    assert service.call_args.args[1:] == (1, 7, 1, 2)


@pytest.mark.parametrize("internal", [False, True])
def test_delete_returns_only_safe_metadata(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    internal: bool,
) -> None:
    prefix, headers = auth(settings, internal)
    stored = record()
    stored.consumed_at, stored.consumed_by = None, None
    stored.revoked_at = stored.created_at + timedelta(minutes=1)
    service = Mock(return_value=stored)
    monkeypatch.setattr(groups, "revoke_invite", service)
    response = client.delete(prefix + "/groups/1/invites/2", headers=headers)
    assert (
        response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    )
    assert set(response.json()) == FIELDS
    assert response.json()["revoked_at"] is not None
    assert stored.token_hash not in response.text
    assert service.call_args.args[1:] == (1, 7, 2)


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize(
    "method,status,code",
    [
        ("GET", 403, "owner_required"),
        ("GET", 404, "group_not_found"),
        ("DELETE", 403, "owner_required"),
        ("DELETE", 404, "invite_invalid"),
        ("DELETE", 409, "invite_consumed"),
    ],
)
def test_management_errors_keep_envelope(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    internal: bool,
    method: str,
    status: int,
    code: str,
) -> None:
    prefix, headers = auth(settings, internal)
    monkeypatch.setattr(
        groups,
        "list_invites" if method == "GET" else "revoke_invite",
        Mock(side_effect=ApiError(status, code, "Request failed")),
    )
    response = client.request(
        method,
        prefix + "/groups/1/invites" + ("/2" if method == "DELETE" else ""),
        headers=headers,
    )
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize(
    "channel",
    ["missing_jwt", "missing_service", "service_on_public", "jwt_on_internal", "mixed"],
)
def test_management_cannot_mix_or_substitute_actor(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    channel: str,
) -> None:
    public, jwt_headers = auth(settings, False)
    internal, service_headers = auth(settings, True)
    prefix, headers, status = {
        "missing_jwt": (public, {}, 401),
        "missing_service": (internal, {"X-Telegram-ID": "123"}, 401),
        "service_on_public": (public, service_headers, 400),
        "jwt_on_internal": (internal, jwt_headers, 400),
        "mixed": (internal, {**jwt_headers, **service_headers}, 400),
    }[channel]
    list_service, revoke_service = Mock(), Mock()
    monkeypatch.setattr(groups, "list_invites", list_service)
    monkeypatch.setattr(groups, "revoke_invite", revoke_service)
    response = client.request(
        method,
        prefix + "/groups/1/invites" + ("/2" if method == "DELETE" else ""),
        headers=headers,
    )
    assert response.status_code == status
    list_service.assert_not_called()
    revoke_service.assert_not_called()


def test_openapi_declares_metadata_only_routes_and_errors(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for prefix in ("", "/internal"):
        path = prefix + "/groups/{group_id}/invites"
        listing = schema["paths"][path]["get"]
        parameters = {p["name"]: p for p in listing["parameters"]}
        assert parameters["limit"]["schema"]["default"] == 20
        assert parameters["limit"]["schema"]["maximum"] == 100
        assert parameters["offset"]["schema"]["minimum"] == 0
        revoke = schema["paths"][path + "/{invite_id}"]["delete"]
        assert set(revoke["responses"]) >= {
            "200",
            "400",
            "401",
            "403",
            "404",
            "409",
            "500",
        }
        assert "422" not in revoke["responses"]
        assert revoke["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/InviteProfile")
        assert (
            revoke["responses"]["409"]["content"]["application/json"]["example"][
                "error"
            ]["code"]
            == "invite_consumed"
        )
        assert listing["security"] == [{"APIKeyHeader" if prefix else "HTTPBearer": []}]
    profile = schema["components"]["schemas"]["InviteProfile"]
    assert set(profile["properties"]) == FIELDS
    assert profile["examples"][0]["revoked_at"] is not None
