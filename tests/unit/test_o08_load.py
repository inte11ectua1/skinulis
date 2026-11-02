"""Load guard correctness is fast and requires no running server."""

import os

import pytest

from scripts.load_o08 import CLIENTS, OPERATIONS, percentile
from scripts.o08_support import isolated_environment, validate_database, validate_target


@pytest.mark.parametrize(
    "target",
    [
        "https://127.0.0.1:1",
        "http://example.com:80",
        "http://127.0.0.1.example.com:80",
        "http://user:pw@localhost:80",  # pragma: allowlist secret (synthetic guard input)
        "http://localhost:80/api",
        "http://localhost:80?target=x",
        "http://localhost:80#x",
        "http://localhost",
        "http://0.0.0.0:8000",
    ],
)
def test_external_or_ambiguous_targets_refused(target: str) -> None:
    with pytest.raises(ValueError):
        validate_target(target)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@example.com:5432/x_test",
        "postgresql+psycopg://u:p@127.0.0.1:5432/production",
        "postgresql+psycopg://u:p@localhost:5432/x_test?host=example.com",
        "postgresql://u:p@localhost:5432/x_test",
        "postgresql+psycopg://u:p@localhost/x_test",
        "not a URL",
    ],
)
def test_external_or_non_test_databases_refused(url: str) -> None:
    with pytest.raises(ValueError):
        validate_database(url)


def test_owned_environment_does_not_inherit_operator_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "BOT_SERVICE_TOKEN",
        "BOT_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "PGPASSWORD",
    ):
        monkeypatch.setenv(name, "synthetic-operator-marker")
    url = validate_database(
        "postgresql+psycopg://u:synthetic@127.0.0.1:5432/skinulis_o08_"  # pragma: allowlist secret (synthetic test URL)
        + "a" * 32
        + "_test",
        owned=True,
    )
    environment = isolated_environment(url)
    assert environment["APP_ENV"] == "test"
    assert all(value != "synthetic-operator-marker" for value in environment.values())
    assert "BOT_TOKEN" not in environment and "AWS_SECRET_ACCESS_KEY" not in environment
    sentinel = "synthetic-operator-marker"
    assert os.environ["JWT_SECRET_KEY"] == sentinel  # pragma: allowlist secret


def test_frozen_profile_and_nearest_rank() -> None:
    assert CLIENTS == 100
    assert len(OPERATIONS) == 10 and OPERATIONS.count("create") == 2
    assert [percentile(list(range(1, 101)), p) for p in (50, 95, 99)] == [50, 95, 99]
    assert percentile([3], 95) == 3
    with pytest.raises(ValueError):
        percentile([], 95)
