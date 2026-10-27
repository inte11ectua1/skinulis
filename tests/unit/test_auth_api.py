import logging
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.security import create_access_token, hash_password
from app.db import get_session
from app.main import create_app
from app.models import User


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(24))
    )


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def password() -> str:
    return secrets.token_urlsafe(24)


@pytest.fixture
def user(password: str) -> User:
    return User(
        id=1,
        email="alice@example.com",
        password_hash=hash_password(password),
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def client(settings: Settings, session: MagicMock) -> Iterator[TestClient]:
    application = create_app(settings)
    application.dependency_overrides[get_session] = lambda: session
    with TestClient(application) as instance:
        yield instance


def assert_error(response: object) -> None:
    # Typed assertions below use the actual httpx response; helpers never echo secrets.
    import httpx

    assert isinstance(response, httpx.Response)
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_registration_hashes_password_and_exposes_only_profile(
    client: TestClient, session: MagicMock, password: str
) -> None:
    def flush() -> None:
        user = session.add.call_args.args[0]
        user.id, user.created_at = 1, datetime.now(UTC)

    session.flush.side_effect = flush
    response = client.post(
        "/auth/register", json={"email": "ALICE@example.com", "password": password}
    )
    assert response.status_code == 201
    assert set(response.json()) == {"id", "email", "telegram_id", "created_at"}
    assert response.json()["email"] == "alice@example.com"
    stored = session.add.call_args.args[0]
    assert stored.password_hash.startswith("$argon2id$")
    assert password not in stored.password_hash + response.text
    session.begin.assert_called_once()


def test_login_and_profile_use_verified_user(
    client: TestClient, session: MagicMock, user: User, password: str
) -> None:
    session.scalar.return_value = user
    session.get.return_value = user
    login = client.post("/auth/login", json={"email": user.email, "password": password})
    assert login.status_code == 200
    assert login.headers["Cache-Control"] == "no-store"
    payload = login.json()
    assert set(payload) == {"access_token", "token_type", "expires_in"}
    assert payload["token_type"] == "bearer" and payload["expires_in"] == 900
    response = client.get(
        "/users/me?user_id=999",
        headers={"Authorization": "Bearer " + payload["access_token"]},
    )
    assert response.status_code == 200 and response.json()["id"] == user.id
    session.get.assert_called_with(User, user.id)
    assert "password" not in response.text


@pytest.mark.parametrize("known", [True, False])
def test_login_failure_does_not_disclose_existence(
    client: TestClient, session: MagicMock, user: User, known: bool
) -> None:
    session.scalar.return_value = user if known else None
    response = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": secrets.token_urlsafe(24)},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert response.json()["error"]["message"] == "Invalid credentials"
    assert_error(response)


def test_telegram_only_cannot_use_password_login(
    client: TestClient, session: MagicMock, password: str
) -> None:
    session.scalar.return_value = User(id=2, telegram_id=123)
    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": password}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization", [None, "Basic abc", "Bearer", "Bearer broken"]
)
def test_profile_rejects_missing_or_malformed_auth(
    client: TestClient, session: MagicMock, authorization: str | None
) -> None:
    response = client.get(
        "/users/me", headers={"Authorization": authorization} if authorization else {}
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert_error(response)
    session.get.assert_not_called()


def test_profile_rejects_missing_user(
    client: TestClient, settings: Settings, session: MagicMock
) -> None:
    session.get.return_value = None
    token = create_access_token(42, settings.require_jwt_secret(), 15)
    response = client.get("/users/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert_error(response)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": "invalid", "password": secrets.token_urlsafe(24)},
        {"email": "alice@example.com", "password": ""},
        {"email": "alice@example.com", "password": 15},
        {"email": "alice@example.com", "password": "x" * 16, "telegram_id": 42},
    ],
)
def test_registration_validation_is_safe_400(
    client: TestClient, session: MagicMock, body: dict[str, object]
) -> None:
    response = client.post("/auth/register", json=body)
    assert response.status_code == 400
    assert_error(response)
    session.add.assert_not_called()


def test_invalid_json_is_safe_400(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        content=b'{"password":',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert_error(response)


@pytest.mark.parametrize("password", ["\ud800", "\x00", " " * 15])
def test_login_rejects_invalid_password_input(
    client: TestClient, password: str
) -> None:
    import json

    response = client.post(
        "/auth/login",
        content=json.dumps({"email": "alice@example.com", "password": password}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert_error(response)


def test_unexpected_error_does_not_log_private_data(
    client: TestClient,
    session: MagicMock,
    password: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private = secrets.token_urlsafe(32)
    session.scalar.side_effect = RuntimeError(private)
    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/auth/login", json={"email": "alice@example.com", "password": password}
        )
    assert response.status_code == 500
    assert_error(response)
    assert private not in response.text + caplog.text
    assert password not in response.text + caplog.text
    assert "Traceback" not in caplog.text


def test_openapi_auth_contract(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    for path in ("/auth/register", "/auth/login"):
        assert "400" in document["paths"][path]["post"]["responses"]
        assert "422" not in document["paths"][path]["post"]["responses"]
    assert document["paths"]["/users/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert (
        "password_hash"
        not in document["components"]["schemas"]["UserProfile"]["properties"]
    )


def test_other_db_constraint_error_is_not_misreported_as_duplicate(
    client: TestClient,
    session: MagicMock,
    password: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private = secrets.token_urlsafe(24)
    session.flush.side_effect = IntegrityError("INSERT", {}, CheckViolation(private))
    response = client.post(
        "/auth/register", json={"email": "alice@example.com", "password": password}
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert private not in response.text + caplog.text
    assert_error(response)
