"""Response timestamps must not inherit the PostgreSQL connection timezone."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.migrate import main as migrate
from app.core.security import create_access_token
from app.db import Database
from app.main import create_app
from app.models import GroupInvite

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
