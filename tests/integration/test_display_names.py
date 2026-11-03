"""Name migration and actor isolation on real PostgreSQL, not SQLite."""

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DataError, IntegrityError

from alembic import command
from tests.integration import test_groups_identity as identity_tests
from tests.integration.test_groups_identity import Harness

pytestmark = pytest.mark.integration


def test_upgrade_preserves_legacy_identities(database_url: URL) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "0006_settlement_notification_claim")
    engine = create_engine(database_url, hide_parameters=True)
    try:
        with engine.begin() as c:
            uid = c.execute(
                text("INSERT INTO users (telegram_id) VALUES (123) RETURNING id")
            ).scalar_one()
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        assert ScriptDirectory.from_config(config).get_heads() == [
            "0007_user_display_name"
        ]
        with engine.connect() as c:
            assert c.execute(
                text("SELECT telegram_id,display_name FROM users WHERE id=:id"),
                {"id": uid},
            ).one() == (123, None)
    finally:
        engine.dispose()


h = identity_tests.h


@pytest.mark.parametrize(
    "name", ["", " ", " padded", "padded ", "x" * 65, "line\nbreak"]
)
def test_name_sql_constraint(h: Harness, name: str) -> None:
    with pytest.raises((IntegrityError, DataError)), h.engine.begin() as c:
        c.execute(
            text("INSERT INTO users (telegram_id,display_name) VALUES (123,:name)"),
            {"name": name},
        )


def test_names_follow_verified_actor_and_never_override_on_repeat(h: Harness) -> None:
    c = h.client
    a = c.post(
        "/internal/users/bootstrap",
        headers=h.service(101),
        json={"display_name": "  Саша  "},
    )
    assert a.status_code == 200
    b = c.post(
        "/internal/users/bootstrap",
        headers=h.service(102),
        json={"display_name": "Саша"},
    )
    assert b.status_code == 200
    assert a.json()["display_name"] == b.json()["display_name"] == "Саша"
    assert (
        c.patch(
            "/internal/users/me",
            headers=h.service(101),
            json={"display_name": "<b>Моё имя</b>"},
        ).status_code
        == 200
    )
    repeat = c.post(
        "/internal/users/bootstrap",
        headers=h.service(101),
        json={"display_name": "Новое имя Telegram"},
    )
    assert repeat.json()["display_name"] == "<b>Моё имя</b>"
    assert (
        c.get("/internal/users/me", headers=h.service(102)).json()["display_name"]
        == "Саша"
    )
    for field in ("user_id", "telegram_id", "owner_id"):
        bad = c.patch(
            "/internal/users/me",
            headers=h.service(101),
            json={"display_name": "Подмена", field: b.json()["id"]},
        )
        assert bad.status_code == 400
    assert (
        c.patch(
            "/internal/users/me",
            headers={"X-Telegram-ID": "101"},
            json={"display_name": "Подмена"},
        ).status_code
        == 401
    )
    assert c.patch("/users/me", json={"display_name": "Подмена"}).status_code == 401
    _, jwt = h.user(None, email="existing@example.com")
    assert (
        c.patch(
            "/users/me", headers=jwt, json={"display_name": "Имя по почте"}
        ).status_code
        == 200
    )
    code = c.post("/users/me/telegram-link-code", headers=jwt, json={}).json()["code"]
    assert (
        c.post(
            "/internal/users/telegram-link", headers=h.service(104), json={"code": code}
        ).json()["display_name"]
        == "Имя по почте"
    )
    assert (
        c.post(
            "/internal/users/bootstrap",
            headers=h.service(104),
            json={"display_name": "Другой Telegram"},
        ).json()["display_name"]
        == "Имя по почте"
    )


def test_member_name_visible_only_to_members(h: Harness) -> None:
    uid, a = h.user(101)
    _, outsider = h.user(102)
    assert (
        h.client.patch(
            "/users/me", headers=a, json={"display_name": "Анна"}
        ).status_code
        == 200
    )
    gid = h.group(a)
    r = h.client.get(f"/groups/{gid}/members", headers=a)
    assert r.status_code == 200 and r.json()["items"][0]["display_name"] == "Анна"
    assert set(r.json()["items"][0]) == {
        "user_id",
        "display_name",
        "joined_at",
        "is_owner",
    }
    assert h.client.get(f"/groups/{gid}/members", headers=outsider).status_code == 404
    assert (
        h.client.get(f"/internal/groups/{gid}/members", headers=h.service(101)).json()[
            "items"
        ][0]["display_name"]
        == "Анна"
    )
