"""Response timestamps must not inherit the PostgreSQL connection timezone."""

import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import cast
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.identity_tokens import new_secret
from app.core.migrate import main as migrate
from app.core.security import create_access_token
from app.db import Database
from app.main import create_app
from app.models import Group, GroupInvite, GroupMember, TelegramLinkCode, User
from bot.api_client import ApiClient

pytestmark = pytest.mark.integration


@pytest.fixture(params=["UTC", "Europe/Moscow"])
def timezone_client(
    database_url: URL, request: pytest.FixtureRequest
) -> Iterator[TestClient]:
    assert migrate() == 0
    zone = str(request.param)
    application = create_app(Settings(_env_file=None))
    with TestClient(application) as client:
        database: Database = application.state.database
        # Only this app's test engine: every API Session uses the requested timezone.
        # No server/database/role settings or production code are changed.
        database.close()
        database.engine = create_engine(
            database_url,
            hide_parameters=True,
            connect_args={"options": f"-c timezone={zone} -c statement_timeout=3000"},
        )
        database.sessions = sessionmaker(database.engine, expire_on_commit=False)
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW TIMEZONE").scalar_one() == zone
        yield client


def service(client: TestClient, telegram_id: int) -> dict[str, str]:
    settings: Settings = cast(FastAPI, client.app).state.settings
    return {
        "X-Bot-Service-Token": settings.require_bot_service_token(),
        "X-Telegram-ID": str(telegram_id),
    }


def owner(client: TestClient) -> tuple[int, dict[str, str]]:
    profile = client.post(
        "/internal/users/bootstrap", headers=service(client, 123), json={}
    )
    assert profile.status_code == 200
    settings: Settings = cast(FastAPI, client.app).state.settings
    uid: int = profile.json()["id"]
    return uid, {
        "Authorization": "Bearer "
        + create_access_token(uid, settings.require_jwt_secret(), 15)
    }


@pytest.mark.parametrize("internal", [False, True])
def test_repeated_delete_has_identical_utc_metadata(
    timezone_client: TestClient, internal: bool
) -> None:
    client = timezone_client
    _, jwt_headers = owner(client)
    prefix, headers = (
        ("/internal", service(client, 123)) if internal else ("", jwt_headers)
    )
    group = client.post(
        prefix + "/groups",
        headers=headers,
        json={"name": "UTC regression", "client_request_id": str(uuid4())},
    )
    assert group.status_code == 201
    path = prefix + f"/groups/{group.json()['id']}/invites"
    issued = client.post(
        path, headers=headers, json={"client_request_id": str(uuid4())}
    )
    assert issued.status_code == 201
    invite_id = issued.json()["id"]
    first = client.delete(path + f"/{invite_id}", headers=headers)
    second = client.delete(path + f"/{invite_id}", headers=headers)
    assert first.status_code == second.status_code == 200
    # Prove the instant is identical even when the old JSON representations differ.
    first_instant = datetime.fromisoformat(first.json()["revoked_at"])
    second_instant = datetime.fromisoformat(second.json()["revoked_at"])
    assert first_instant == second_instant
    database: Database = cast(FastAPI, client.app).state.database
    with database.sessions() as session:
        stored = session.get(GroupInvite, invite_id)
        assert stored is not None and stored.revoked_at == first_instant
        assert stored.expires_at - stored.created_at == timedelta(hours=24)
    assert first.content == second.content
    assert first.json()["revoked_at"].endswith("Z")


def assert_utc_fields(value: object) -> None:
    if isinstance(value, dict):
        for name, item in value.items():
            if (
                name
                in {
                    "created_at",
                    "joined_at",
                    "expires_at",
                    "consumed_at",
                    "revoked_at",
                }
                and item is not None
            ):
                assert isinstance(item, str) and item.endswith("Z")
                assert datetime.fromisoformat(item).utcoffset() == timedelta(0)
            else:
                assert_utc_fields(item)
    elif isinstance(value, list):
        for item in value:
            assert_utc_fields(item)


def checked(response: httpx.Response, status: int = 200) -> httpx.Response:
    assert response.status_code == status
    assert_utc_fields(response.json())
    return response


def test_identity_and_group_timestamps_preserve_instants_and_ttls(
    timezone_client: TestClient,
) -> None:
    client = timezone_client
    database: Database = cast(FastAPI, client.app).state.database
    payload = {"email": "utc@example.com", "password": new_secret()}
    registered = checked(client.post("/auth/register", json=payload), 201).json()
    login = checked(client.post("/auth/login", json=payload)).json()
    jwt_headers = {"Authorization": "Bearer " + login["access_token"]}
    assert checked(client.get("/users/me", headers=jwt_headers)).json() == registered
    code = checked(
        client.post("/users/me/telegram-link-code", headers=jwt_headers, json={}), 201
    ).json()
    with database.sessions() as session:
        stored_code = session.scalar(
            select(TelegramLinkCode).where(TelegramLinkCode.user_id == registered["id"])
        )
        assert stored_code is not None
        assert stored_code.expires_at == datetime.fromisoformat(code["expires_at"])
        assert stored_code.expires_at - stored_code.created_at == timedelta(minutes=10)
    linked = checked(
        client.post(
            "/internal/users/telegram-link",
            headers=service(client, 123),
            json={"code": code["code"]},
        )
    ).json()
    assert linked["created_at"] == registered["created_at"]
    assert (
        checked(client.get("/internal/users/me", headers=service(client, 123))).json()
        == linked
    )
    assert (
        checked(
            client.post(
                "/internal/users/bootstrap", headers=service(client, 123), json={}
            )
        ).json()
        == linked
    )
    checked(
        client.post("/internal/users/bootstrap", headers=service(client, 456), json={})
    )
    for prefix, headers in (("", jwt_headers), ("/internal", service(client, 123))):
        body = {"name": "UTC group", "client_request_id": str(uuid4())}
        created = checked(
            client.post(prefix + "/groups", headers=headers, json=body), 201
        ).json()
        assert (
            checked(
                client.post(prefix + "/groups", headers=headers, json=body), 201
            ).json()
            == created
        )
        gid = created["id"]
        assert (
            checked(client.get(prefix + f"/groups/{gid}", headers=headers)).json()
            == created
        )
        checked(client.get(prefix + "/groups", headers=headers))
        members = checked(
            client.get(prefix + f"/groups/{gid}/members", headers=headers)
        ).json()["items"]
        invite_path = prefix + f"/groups/{gid}/invites"
        request_key = {"client_request_id": str(uuid4())}
        issued = checked(
            client.post(invite_path, headers=headers, json=request_key), 201
        ).json()
        replay = checked(
            client.post(invite_path, headers=headers, json=request_key), 201
        ).json()
        assert replay == {**issued, "token": None}
        consumed = checked(
            client.post(
                "/internal/group-invites/join",
                headers=service(client, 456),
                json={"token": issued["token"]},
            )
        ).json()
        assert consumed["id"] == gid
        second = checked(
            client.post(
                invite_path, headers=headers, json={"client_request_id": str(uuid4())}
            ),
            201,
        ).json()
        first_delete = checked(
            client.delete(invite_path + f"/{second['id']}", headers=headers)
        )
        repeated_delete = checked(
            client.delete(invite_path + f"/{second['id']}", headers=headers)
        )
        assert first_delete.content == repeated_delete.content
        listing = checked(client.get(invite_path, headers=headers)).json()["items"]
        used = next(item for item in listing if item["id"] == issued["id"])
        revoked = next(item for item in listing if item["id"] == second["id"])
        assert used["consumed_at"] is not None and revoked == first_delete.json()
        with database.sessions() as session:
            user = session.get(User, registered["id"])
            group = session.get(Group, gid)
            membership = session.get(GroupMember, (gid, registered["id"]))
            stored = session.get(GroupInvite, issued["id"])
            assert user is not None and user.created_at == datetime.fromisoformat(
                linked["created_at"]
            )
            assert group is not None and group.created_at == datetime.fromisoformat(
                created["created_at"]
            )
            assert (
                membership is not None
                and membership.joined_at
                == datetime.fromisoformat(members[0]["joined_at"])
            )
            assert stored is not None and stored.created_at == datetime.fromisoformat(
                issued["created_at"]
            )
            assert stored.expires_at == datetime.fromisoformat(issued["expires_at"])
            assert stored.consumed_at == datetime.fromisoformat(used["consumed_at"])
            assert stored.expires_at - stored.created_at == timedelta(hours=24)

        parsed_dates = asyncio.run(read_with_lera_client(client, gid, second["id"]))
        assert parsed_dates == (
            datetime.fromisoformat(linked["created_at"]),
            datetime.fromisoformat(created["created_at"]),
            datetime.fromisoformat(members[0]["joined_at"]),
            datetime.fromisoformat(revoked["revoked_at"]),
        )


async def read_with_lera_client(
    client: TestClient, group_id: int, invite_id: int
) -> tuple[datetime, datetime, datetime, datetime | None]:
    application = cast(FastAPI, client.app)
    settings: Settings = application.state.settings
    # Actual unmodified client/DTO parsing, served by this real PG-backed app.
    async with ApiClient(
        "http://testserver",
        service_token=settings.bot_service_token,
        transport=httpx.ASGITransport(app=application),
    ) as api:
        profile = await api.profile(123)
        group = await api.group(123, group_id)
        assert (await api.groups(123)).items
        members = (await api.members(123, group_id)).items
        invites = (await api.invites(123, group_id)).items
        assert all(
            value.utcoffset() == timedelta(0)
            for item in invites
            for value in (
                item.created_at,
                item.expires_at,
                item.consumed_at,
                item.revoked_at,
            )
            if value is not None
        )
        revoked = await api.revoke_invite(123, group_id, invite_id)
        dates = (
            profile.created_at,
            group.created_at,
            members[0].joined_at,
            revoked.revoked_at,
        )
        assert all(
            value.utcoffset() == timedelta(0) for value in dates if value is not None
        )
        return dates
