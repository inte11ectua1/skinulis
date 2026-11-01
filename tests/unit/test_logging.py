"""Privacy is an allowlist projection, including framework/driver failures."""

import asyncio
import json
import logging
import secrets
from datetime import datetime
from typing import Literal, cast
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alembic import command
from app.config import Settings
from app.core import migrate, serve
from app.core.errors import ApiError
from app.main import create_app
from bot.api_client import ApiClient
from bot.api_client import ApiError as ClientError
from bot.main import telegram_outcome
from skinulis_logging import (
    Event,
    Fields,
    JsonFormatter,
    Outcome,
    canonical_request_id,
    configure_logging,
    current_request_id,
    emit,
    register_routes,
    request_context,
)


def records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    captured = capsys.readouterr()
    assert not captured.err
    return [json.loads(line) for line in captured.out.splitlines()]


@pytest.fixture
def application() -> FastAPI:
    app = create_app(
        Settings(_env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(32)))
    )

    @app.get("/diagnostic/{status}")
    def diagnostic(status: int) -> dict[str, bool]:
        if status == 500:
            raise RuntimeError("private-exception-detail")
        if status != 200:
            raise ApiError(status, "test_error", "Request failed")
        return {"ok": True}

    register_routes([*app.openapi()["paths"], "/diagnostic/{status}"])
    return app


@pytest.mark.parametrize("service", ["api", "bot"])
def test_json_format_projects_only_safe_fields(
    service: Literal["api", "bot"], capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(service)
    register_routes(["/groups/{group_id}"])
    with request_context() as request_id:
        emit(
            Event.HTTP_COMPLETED,
            fields=Fields(
                status=200, method="GET", route="/groups/{group_id}", duration_ms=2
            ),
        )
    entry = records(capsys)[0]
    assert entry == {
        "timestamp": entry["timestamp"],
        "level": "info",
        "service": service,
        "event": "http_request_completed",
        "request_id": request_id,
        "status": 200,
        "method": "GET",
        "route": "/groups/{group_id}",
        "duration_ms": 2,
    }
    assert str(entry["timestamp"]).endswith("Z")
    offset = datetime.fromisoformat(str(entry["timestamp"])).utcoffset()
    assert offset is not None and offset.total_seconds() == 0


@pytest.mark.parametrize(
    "name",
    [
        "skinulis",
        "uvicorn.error",
        "httpx",
        "sqlalchemy.engine",
        "psycopg",
        "aiogram.event",
        "py.warnings",
    ],
)
def test_exception_args_headers_extra_and_stack_are_never_serialized(
    name: str, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging("api")
    private = secrets.token_urlsafe(48)
    try:
        raise RuntimeError(private)
    except RuntimeError:
        logging.getLogger(name).exception(
            "Authorization: Bearer %s",
            private,
            extra={
                "password": private,
                "settlement_amount": "123456.78",
                "invite_link": "https://t.me/test?start=" + private,
                "headers": {"X-Bot-Service-Token": private},
                "body": private,
            },
            stack_info=True,
        )
    output = records(capsys)
    assert len(output) == 1
    assert private not in json.dumps(output) + caplog.text
    assert "Traceback" not in json.dumps(output) + caplog.text
    assert set(output[0]) == {"timestamp", "level", "service", "event", "request_id"}


@pytest.mark.parametrize(
    "value",
    [None, "", "injected\nsecret", str(uuid4()).upper(), "0" * 36, "1234", [], {}],
)
def test_invalid_correlation_is_not_accepted(value: object) -> None:
    assert canonical_request_id(value) is None


def test_formatter_does_not_stringify_untrusted_objects() -> None:
    class Poison:
        def __str__(self) -> str:
            raise AssertionError("A private object must never be stringified")

    record = logging.LogRecord("foreign", logging.ERROR, "", 0, Poison(), (), None)
    record.safe_fields = Fields(
        method=cast(str, []),
        route=cast(str, {}),
        status=cast(int, True),
        duration_ms=-1,
        request_id="unsafe",
        outcome=cast(Outcome, Poison()),
    )
    entry = json.loads(JsonFormatter("api").format(record))
    assert set(entry) == {"timestamp", "level", "service", "event", "request_id"}
    assert entry["event"] == "library_event"


@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 409, 500])
def test_http_correlation_and_safe_errors(
    application: FastAPI, status: int, capsys: pytest.CaptureFixture[str]
) -> None:
    injected = str(uuid4())
    with TestClient(application) as client:
        capsys.readouterr()
        response = client.get(
            f"/diagnostic/{status}?password=private-query",
            headers={"X-Request-ID": injected, "Authorization": "Bearer private-jwt"},
        )
        entries = records(capsys)
    request_id = response.headers["X-Request-ID"]
    assert canonical_request_id(request_id) and request_id != injected
    assert response.status_code == status
    if status != 200:
        assert response.json()["error"]["request_id"] == request_id
        assert response.headers["Cache-Control"] == "no-store"
    completed = next(e for e in entries if e["event"] == "http_request_completed")
    assert completed["request_id"] == request_id
    assert completed["status"] == status
    assert completed["route"] == "/diagnostic/{status}"
    assert all(e["request_id"] == request_id for e in entries)
    assert "private-" not in json.dumps(entries) + response.text


@pytest.mark.parametrize(
    "path", ["/users/me", "/internal/users/me", "/internal/users/bootstrap"]
)
def test_auth_and_service_failures_do_not_log_credentials(
    application: FastAPI, path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    private = secrets.token_urlsafe(32)
    with TestClient(application) as client:
        capsys.readouterr()
        response = client.request(
            "POST" if path.endswith("bootstrap") else "GET",
            path,
            headers={"Authorization": "Bearer " + private}
            if path == "/users/me"
            else {
                "X-Bot-Service-Token": private,
                "X-Telegram-ID": "9223372036854775807",
            },
            json={},
        )
        entries = records(capsys)
    assert response.status_code == 401
    assert entries[-1]["request_id"] == response.json()["error"]["request_id"]
    assert private not in json.dumps(entries)
    assert "9223372036854775807" not in json.dumps(entries)


def test_validation_and_database_failures_are_sanitized(
    application: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = secrets.token_urlsafe(32)
    with TestClient(application) as client:
        capsys.readouterr()
        invalid = client.post(
            "/auth/register",
            json={"email": private, "password": private, "amount": private},
        )
        assert invalid.status_code == 400
        assert private not in json.dumps(records(capsys))
        monkeypatch.setattr(
            Session,
            "execute",
            Mock(
                side_effect=OperationalError(
                    "SELECT :secret", {"secret": private}, RuntimeError(private)
                )
            ),
        )
        response = client.get("/health")
        entries = records(capsys)
    assert response.status_code == 503
    assert {e["event"] for e in entries} == {
        "database_unavailable",
        "http_request_completed",
    }
    assert all(e["request_id"] == response.headers["X-Request-ID"] for e in entries)
    assert private not in json.dumps(entries) + response.text


def test_concurrent_http_requests_keep_separate_contexts(
    application: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    async def concurrent() -> list[httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            return list(
                await asyncio.gather(
                    *(client.get("/diagnostic/200") for _ in range(12))
                )
            )

    responses = asyncio.run(concurrent())
    entries = records(capsys)
    ids = {r.headers["X-Request-ID"] for r in responses}
    assert len(ids) == 12
    assert {e["request_id"] for e in entries} == ids
    assert current_request_id() not in ids


@pytest.mark.parametrize("failure", ["timeout", "network", "response", "success"])
def test_bot_http_logs_safe_outcome_and_response_correlation(
    failure: str, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("bot")
    private = secrets.token_urlsafe(32)
    request_id = str(uuid4())

    def transport(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout(private, request=request)
        if failure == "network":
            raise httpx.ConnectError(private, request=request)
        return httpx.Response(
            200 if failure == "success" else 500,
            headers={"X-Request-ID": request_id},
            json={"status": "ok", "database": "ok"}
            if failure == "success"
            else {
                "error": {"code": private, "message": private, "request_id": private}
            },
        )

    async def run() -> None:
        async with ApiClient(
            "http://api.test", transport=httpx.MockTransport(transport)
        ) as client:
            if failure == "success":
                await client.health()
            else:
                with pytest.raises(ClientError):
                    await client.health()

    asyncio.run(run())
    entry = records(capsys)[0]
    assert private not in json.dumps(entry)
    assert entry["service"] == "bot"
    assert entry["outcome"] == {"success": "ok", "response": "server"}.get(
        failure, failure
    )
    assert canonical_request_id(entry["request_id"])
    if failure in {"response", "success"}:
        assert entry["request_id"] == request_id


@pytest.mark.parametrize("failure", [False, True])
def test_migration_events_do_not_expose_driver_errors(
    failure: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private = secrets.token_urlsafe(32)
    upgrade = Mock(side_effect=RuntimeError(private) if failure else None)
    monkeypatch.setattr(command, "upgrade", upgrade)
    assert migrate.main() == int(failure)
    assert upgrade.call_args.args[0].attributes["safe_logging"] is True
    entries = records(capsys)
    assert entries[0]["event"] == "migration_started"
    assert entries[-1]["event"] == (
        "migration_failed" if failure else "migration_completed"
    )
    assert private not in json.dumps(entries)


def test_api_server_uses_safe_logging_and_access_log_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Mock(side_effect=RuntimeError(secrets.token_urlsafe(32)))
    monkeypatch.setattr(uvicorn, "run", run)
    with pytest.raises(SystemExit) as failure:
        serve.main()
    assert failure.value.code == 1
    assert run.call_args.kwargs["access_log"] is False
    assert run.call_args.kwargs["log_config"] is None
    assert records(capsys)[0]["event"] == "api_runtime_failed"


def test_telegram_failure_classification() -> None:
    from aiogram.exceptions import (
        TelegramBadRequest,
        TelegramNetworkError,
        TelegramRetryAfter,
    )
    from aiogram.methods import GetMe

    method = GetMe()
    assert telegram_outcome(TimeoutError()) == Outcome.TIMEOUT
    assert (
        telegram_outcome(
            TelegramRetryAfter(method=method, message="private", retry_after=1)
        )
        == Outcome.RETRY
    )
    assert (
        telegram_outcome(TelegramNetworkError(method=method, message="private"))
        == Outcome.NETWORK
    )
    assert (
        telegram_outcome(TelegramBadRequest(method=method, message="private"))
        == Outcome.TELEGRAM
    )
    assert telegram_outcome(RuntimeError("private")) == Outcome.UNEXPECTED


def test_reconfiguration_does_not_duplicate_records_or_leave_events_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api")
    logging.getLogger("skinulis").disabled = True
    configure_logging("bot")
    configure_logging("bot")
    emit(Event.BOT_STARTED)
    (entry,) = records(capsys)
    assert entry["service"] == "bot"
    assert entry["event"] == "bot_started"


def test_bot_update_failure_keeps_context_and_does_not_leak(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from typing import Any

    from aiogram.types import Update

    from bot.middleware import DeliveredUpdates

    configure_logging("bot")
    private = secrets.token_urlsafe(32)

    async def handler(event: Any, data: dict[str, Any]) -> None:
        raise RuntimeError(private)

    async def run() -> None:
        middleware = DeliveredUpdates()
        with pytest.raises(RuntimeError):
            await middleware(handler, Update(update_id=987654321), {})
        # Existing dedup behavior is preserved after the uncertain failed update.
        await middleware(handler, Update(update_id=987654321), {})

    asyncio.run(run())
    (entry,) = records(capsys)
    assert entry["event"] == "bot_update_failed"
    assert canonical_request_id(entry["request_id"])
    assert private not in json.dumps(entry)
    assert "987654321" not in json.dumps(entry)
