from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import QueuePool

from alembic import command
from app.config import Settings
from app.core.migrate import main as migrate
from app.db import Database
from app.main import create_app

pytestmark = pytest.mark.integration


def test_migrations_on_empty_database_are_repeatable(database_url: URL) -> None:
    engine = create_engine(database_url)
    try:
        assert inspect(engine).get_table_names() == []
        assert migrate() == 0
        assert migrate() == 0
        assert inspect(engine).get_table_names() == ["alembic_version"]
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == "0001_baseline"
            )
        command.check(Config(str(Path("alembic.ini").resolve())))
    finally:
        engine.dispose()


def test_health_queries_real_postgres_and_releases_session(database_url: URL) -> None:
    assert migrate() == 0
    settings = Settings(_env_file=None)
    application = create_app(settings)
    with TestClient(application) as client:
        for _ in range(2):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "database": "ok"}
            database: Database = application.state.database
            pool = database.engine.pool
            assert isinstance(pool, QueuePool)
            assert pool.checkedout() == 0


def test_transaction_commit_rollback_and_close(database_url: URL) -> None:
    database = Database(Settings(_env_file=None))
    try:
        with database.engine.begin() as connection:
            connection.execute(text("CREATE TABLE transaction_probe (value integer)"))
        with database.sessions() as session, session.begin():
            session.execute(text("INSERT INTO transaction_probe VALUES (1)"))
        with pytest.raises(RuntimeError, match="rollback"):
            with database.sessions() as session, session.begin():
                session.execute(text("INSERT INTO transaction_probe VALUES (2)"))
                raise RuntimeError("rollback")
        with database.sessions() as session:
            session.execute(text("INSERT INTO transaction_probe VALUES (3)"))
            # Deliberately uncommitted; context exit must roll it back.
        with database.sessions() as session:
            assert session.execute(
                text("SELECT value FROM transaction_probe")
            ).scalars().all() == [1]
    finally:
        database.close()


def test_unreachable_postgres_returns_503_and_migration_fails(
    database_url: URL,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken_url = database_url.set(host="127.0.0.1", port=1)
    raw_url = broken_url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", raw_url)
    settings = Settings(_env_file=None, database_url=SecretStr(raw_url))
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_unavailable"
        assert database_url.password not in response.text
    assert migrate() == 1
    output = capsys.readouterr()
    assert raw_url not in output.err
    assert "Traceback" not in output.err
