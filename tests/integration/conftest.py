"""Каждый тест получает новую БД; указанная оператором БД не удаляется."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[URL]:
    configured = os.environ.get("TEST_DATABASE_URL")
    if not configured:
        pytest.fail("Integration tests require TEST_DATABASE_URL (see README)")
    admin_url = make_url(configured)
    if (
        admin_url.drivername != "postgresql+psycopg"
        or not admin_url.database
        or not admin_url.database.endswith("_test")
    ):
        pytest.fail("TEST_DATABASE_URL must use psycopg and a database ending in _test")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    name = "skinulis_t03_test_" + uuid4().hex
    with admin.connect() as connection:
        version = int(
            connection.exec_driver_sql("SHOW server_version_num").scalar_one()
        )
        assert 170000 <= version < 180000, "Tests require PostgreSQL 17"
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    isolated_url = admin_url.set(database=name)
    monkeypatch.setenv(
        "DATABASE_URL", isolated_url.render_as_string(hide_password=False)
    )
    try:
        yield isolated_url
    finally:
        # Only the UUID-named database created by this fixture is removed.
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()
