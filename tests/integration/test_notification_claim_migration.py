"""Exact 0005 -> 0006 historical backfill, version metadata and reversible schema."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import DateTime, String, create_engine, inspect, text
from sqlalchemy.engine import URL

from alembic import command
from app.config import Settings
from app.core.security import create_access_token
from app.main import create_app

pytestmark = pytest.mark.integration
HEAD = "0006_settlement_notification_claim"
PREVIOUS = "0005_expense_replay_version"


def test_backfill_all_old_statuses_new_null_and_downgrade_reupgrade(
    database_url: URL,
) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, PREVIOUS)
    engine = create_engine(database_url, hide_parameters=True)
    created = datetime(2026, 10, 30, tzinfo=UTC)
    try:
        with engine.begin() as c:
            c.execute(
                text("INSERT INTO users (id,telegram_id) VALUES (10,123456789),(20,20)")
            )
            gid = c.execute(
                text(
                    "INSERT INTO groups (owner_id,name,client_request_id) VALUES (10,'Legacy',:key) RETURNING id"
                ),
                {"key": uuid4()},
            ).scalar_one()
            c.execute(
                text(
                    "INSERT INTO group_members (group_id,user_id,slot) VALUES (:gid,10,1),(:gid,20,2)"
                ),
                {"gid": gid},
            )
            for status in ("pending", "confirmed", "rejected", "cancelled"):
                c.execute(
                    text(
                        "INSERT INTO settlements (group_id,sender_id,receiver_id,amount_kopecks,status,client_request_id,created_at,resolved_at) VALUES (:gid,20,10,100,:status,:key,:created,:resolved)"
                    ),
                    dict(
                        gid=gid,
                        status=status,
                        key=uuid4(),
                        created=created,
                        resolved=None
                        if status == "pending"
                        else created + timedelta(minutes=1),
                    ),
                )
            before = [
                dict(r)
                for r in c.execute(
                    text("SELECT * FROM settlements ORDER BY id")
                ).mappings()
            ]
        version_type = inspect(engine).get_columns("alembic_version")[0]["type"]
        assert isinstance(version_type, String) and version_type.length == 32
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert ScriptDirectory.from_config(config).get_heads() == [HEAD]
        command.check(config)
        with engine.connect() as c:
            after = [
                dict(r)
                for r in c.execute(
                    text("SELECT * FROM settlements ORDER BY id")
                ).mappings()
            ]
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        for original, backfilled in zip(before, after, strict=True):
            assert {key: backfilled[key] for key in original} == original
            assert backfilled["notification_claimed_at"] == original["created_at"]
        settings = Settings(_env_file=None)
        service = {
            "X-Bot-Service-Token": settings.require_bot_service_token(),
            "X-Telegram-ID": "20",
        }
        with TestClient(create_app(settings)) as client:
            for row in before:
                r = client.post(
                    f"/internal/settlements/{row['id']}/notification-claim",
                    headers=service,
                )
                assert r.status_code == 204 and r.content == b""
            pending = before[0]
            replay = client.post(
                f"/groups/{gid}/settlements",
                json=dict(
                    receiver_id=10,
                    amount="1.00",
                    client_request_id=str(pending["client_request_id"]),
                ),
                headers={
                    "Authorization": "Bearer "
                    + create_access_token(20, settings.require_jwt_secret(), 15)
                },
            )
            assert (
                replay.status_code == 200
                and replay.json()["settlement"]["status"] == "pending"
            )
            assert (
                client.post(
                    f"/internal/settlements/{pending['id']}/notification-claim",
                    headers=service,
                ).status_code
                == 204
            )
        with engine.begin() as c:
            inserted = c.execute(
                text(
                    "INSERT INTO settlements (group_id,sender_id,receiver_id,amount_kopecks,client_request_id) VALUES (:gid,20,10,1,:key) RETURNING notification_claimed_at"
                ),
                {"gid": gid, "key": uuid4()},
            ).one()
            assert inserted.notification_claimed_at is None
        command.downgrade(config, PREVIOUS)
        assert "notification_claimed_at" not in {
            col["name"] for col in inspect(engine).get_columns("settlements")
        }
        with engine.connect() as c:
            assert [
                dict(r)
                for r in c.execute(
                    text("SELECT * FROM settlements ORDER BY id LIMIT 4")
                ).mappings()
            ] == before
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as c:
            assert (
                c.scalar(
                    text(
                        "SELECT count(*) FROM settlements WHERE notification_claimed_at IS NULL"
                    )
                )
                == 0
            )
            assert c.scalar(text("SELECT count(*) FROM settlements")) == 5
    finally:
        engine.dispose()


def test_fresh_repeat_upgrade_nullable_timestamptz_and_schema_check(
    database_url: URL,
) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    engine = create_engine(database_url, hide_parameters=True)
    try:
        column = next(
            col
            for col in inspect(engine).get_columns("settlements")
            if col["name"] == "notification_claimed_at"
        )
        assert isinstance(column["type"], DateTime) and column["type"].timezone
        assert column["nullable"] and column["default"] is None
        version_type = inspect(engine).get_columns("alembic_version")[0]["type"]
        assert isinstance(version_type, String) and version_type.length == 64
        command.check(config)
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
