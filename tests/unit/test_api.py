import logging
import secrets
import tomllib
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    url = URL.create(
        "postgresql+psycopg",
        username="test",
        password=secrets.token_urlsafe(16),
        host="127.0.0.1",
        port=1,
        database="skinulis_test",
    )
    return Settings(
        _env_file=None,
        database_url=SecretStr(url.render_as_string(hide_password=False)),
        app_commit_sha=None,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as instance:
        yield instance


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "skinulis", "docs": "/docs"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_documentation(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200


def test_openapi_declares_health_error(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "503" in schema["paths"]["/health"]["get"]["responses"]
    assert schema["info"]["version"] == __version__


def test_version_without_sha(client: TestClient) -> None:
    assert client.get("/version").json() == {
        "version": __version__,
        "commit_sha": None,
    }


def test_public_version_matches_project_metadata() -> None:
    project = Path(__file__).resolve().parents[2] / "pyproject.toml"
    assert __version__ == tomllib.loads(project.read_text())["project"]["version"]


def test_explicit_sha(settings: Settings) -> None:
    settings.app_commit_sha = "a" * 40
    with TestClient(create_app(settings)) as client:
        assert client.get("/version").json()["commit_sha"] == "a" * 40


def test_health_with_mocked_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    execute = Mock()
    monkeypatch.setattr(Session, "execute", execute)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert str(execute.call_args.args[0]) == "SELECT 1"


def test_health_error_is_sanitized(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_details = secrets.token_urlsafe(32)
    monkeypatch.setattr(
        Session,
        "execute",
        Mock(side_effect=OperationalError("SELECT 1", {}, Exception(private_details))),
    )
    with caplog.at_level(logging.WARNING):
        response = client.get("/health")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "database_unavailable"
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert private_details not in response.text
    assert private_details not in caplog.text
    assert "Traceback" not in caplog.text


def test_component_password_is_escaped_and_hidden() -> None:
    password = secrets.token_urlsafe(16) + "@:/%?#"
    settings = Settings(
        _env_file=None, database_url=None, postgres_password=SecretStr(password)
    )
    assert settings.get_database_url().password == password
    assert password not in repr(settings)
    assert password not in str(settings.get_database_url())


@pytest.mark.parametrize(
    "url", ["sqlite://", "postgresql+psycopg://localhost/db", "broken"]
)
def test_invalid_database_configuration_is_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=SecretStr(url))


@pytest.mark.parametrize("password", [None, SecretStr("")])
def test_missing_database_credentials_fail_safely(password: SecretStr | None) -> None:
    with pytest.raises(ValidationError, match="Set DATABASE_URL"):
        Settings(_env_file=None, database_url=None, postgres_password=password)
