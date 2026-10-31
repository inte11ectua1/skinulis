"""0004 -> 0005 preserves legacy financial rows without inventing POST history."""

from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from alembic import command

pytestmark = pytest.mark.integration


def test_upgrade_legacy_financial_data_repeat_check_and_downgrade(
    database_url: URL,
) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "0004_financial_domain")
    engine = create_engine(database_url, hide_parameters=True)
    try:
        with engine.begin() as conn:
            uid = conn.execute(
                text("INSERT INTO users (telegram_id) VALUES (123) RETURNING id")
            ).scalar_one()
            gid = conn.execute(
                text(
                    "INSERT INTO groups (owner_id,name,client_request_id) VALUES (:uid,'Legacy',:key) RETURNING id"
                ),
                {"uid": uid, "key": uuid4()},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO group_members (group_id,user_id,slot) VALUES (:gid,:uid,1)"
                ),
                {"gid": gid, "uid": uid},
            )
            eid = conn.execute(
                text(
                    "INSERT INTO expenses (group_id,payer_id,title,split_mode,amount_kopecks,client_request_id) VALUES (:gid,:uid,'Old receipt','equal',100,:key) RETURNING id"
                ),
                {"gid": gid, "uid": uid, "key": uuid4()},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO expense_shares (expense_id,user_id,group_id,amount_kopecks) VALUES (:eid,:uid,:gid,100)"
                ),
                {"eid": eid, "uid": uid, "gid": gid},
            )
            before = (
                conn.execute(text("SELECT * FROM expenses WHERE id=:eid"), {"eid": eid})
                .mappings()
                .one()
            )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert ScriptDirectory.from_config(config).get_heads() == [
            "0006_settlement_notification_claim"
        ]
        command.check(config)
        with engine.connect() as conn:
            after = (
                conn.execute(text("SELECT * FROM expenses WHERE id=:eid"), {"eid": eid})
                .mappings()
                .one()
            )
            assert {key: after[key] for key in before} == dict(before)
            assert after["version"] == 1
            assert (
                after["initial_create_intent"] is None
                and after["initial_create_result"] is None
            )
            assert (
                conn.execute(
                    text(
                        "SELECT amount_kopecks FROM expense_shares WHERE expense_id=:eid"
                    ),
                    {"eid": eid},
                ).scalar_one()
                == 100
            )
        for version in (0, -1):
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(
                    text("UPDATE expenses SET version=:version WHERE id=:eid"),
                    {"version": version, "eid": eid},
                )
        columns = {col["name"]: col for col in inspect(engine).get_columns("expenses")}
        assert not columns["version"]["nullable"]
        assert (
            columns["initial_create_intent"]["nullable"]
            and columns["initial_create_result"]["nullable"]
        )
        assert str(columns["initial_create_intent"]["type"]) == "JSONB"
        command.downgrade(config, "0004_financial_domain")
        with engine.connect() as conn:
            assert (
                conn.execute(text("SELECT * FROM expenses WHERE id=:eid"), {"eid": eid})
                .mappings()
                .one()
                == before
            )
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
