import asyncio
import logging
import secrets
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.main import create_app
from bot import api_client
from bot.api_client import ApiClient, ApiError, ApiFailure


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def health_payload() -> dict[str, str]:
    # T-03 GET /health, not a hypothetical profile/finance fixture.
    return {"status": "ok", "database": "ok"}


@pytest.mark.anyio
async def test_health_request_reuse_timeout_and_close(
    health_payload: dict[str, str],
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/health"
        assert not request.content
        assert "authorization" not in request.headers
        assert all(0 < value <= 5 for value in request.extensions["timeout"].values())
        return httpx.Response(200, json=health_payload)

    client = ApiClient("http://api.test", transport=httpx.MockTransport(respond))
    async with client:
        assert (await client.health()).model_dump() == health_payload
        assert (await client.health()).status == "ok"
        assert not client.is_closed
    assert client.is_closed
    assert len(requests) == 2
    await client.aclose()  # idempotent cleanup
    with pytest.raises(ApiError) as caught:
        await client.health()
    assert caught.value.kind == ApiFailure.NETWORK


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, ApiFailure.INPUT),
        (401, ApiFailure.AUTH),
        (403, ApiFailure.FORBIDDEN),
        (404, ApiFailure.MISSING),
        (409, ApiFailure.CONFLICT),
        (500, ApiFailure.SERVER),
        (502, ApiFailure.SERVER),
        (503, ApiFailure.SERVER),
        (504, ApiFailure.SERVER),
        (599, ApiFailure.SERVER),
    ],
)
async def test_http_errors_are_safe(
    status: int, kind: ApiFailure, caplog: pytest.LogCaptureFixture
) -> None:
    private = secrets.token_urlsafe(32)
    payload = {
        "error": {
            "code": "test_error",
            "message": "Traceback http://internal/" + private,
            "request_id": "test-request",
        }
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    with caplog.at_level(logging.DEBUG):
        async with ApiClient("http://api.test", transport=transport) as client:
            with pytest.raises(ApiError) as caught:
                await client.health()
    error = caught.value
    assert error.kind == kind
    assert error.status_code == status
    assert error.error_code == "test_error"
    assert error.request_id == "test-request"
    assert private not in str(error) + repr(error) + caplog.text
    assert "Traceback" not in str(error) + repr(error) + caplog.text
    assert "internal" not in str(error) + repr(error)
    assert client.is_closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
    ],
)
async def test_transport_errors(failure: type[httpx.RequestError]) -> None:
    private = secrets.token_urlsafe(32)
    calls = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise failure(private, request=request)

    async with ApiClient(
        "http://api.test", transport=httpx.MockTransport(fail)
    ) as client:
        with pytest.raises(ApiError) as caught:
            await client.health()
    expected = (
        ApiFailure.TIMEOUT
        if issubclass(failure, httpx.TimeoutException)
        else ApiFailure.NETWORK
    )
    assert caught.value.kind == expected
    assert private not in str(caught.value) + repr(caught.value)
    assert calls == 1  # no implicit retries


@pytest.mark.anyio
async def test_total_deadline_also_bounds_a_stalled_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_client, "TOTAL_TIMEOUT", 0.01)

    async def stalled(_: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async with ApiClient(
        "http://api.test", transport=httpx.MockTransport(stalled)
    ) as client:
        with pytest.raises(ApiError) as caught:
            await client.health()
    assert caught.value.kind == ApiFailure.TIMEOUT
    assert client.is_closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        b"<html>unavailable</html>",
        b"{}",
        b"[]",
        b"null",
        b'{"status":"ok"}',
        b'{"status":"error","database":"ok"}',
        b'{"status":true,"database":"ok"}',
    ],
)
async def test_unexpected_success_body(body: bytes) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    async with ApiClient("http://api.test", transport=transport) as client:
        with pytest.raises(ApiError) as caught:
            await client.health()
    assert caught.value.kind == ApiFailure.UNEXPECTED


@pytest.mark.anyio
@pytest.mark.parametrize("status", [201, 204, 302, 418, 429])
async def test_unexpected_status_is_not_success(status: int) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status))
    async with ApiClient("http://api.test", transport=transport) as client:
        with pytest.raises(ApiError) as caught:
            await client.health()
    assert caught.value.kind == ApiFailure.UNEXPECTED
    assert caught.value.status_code == status


@pytest.mark.anyio
@pytest.mark.parametrize("body", [b"not json", b'{"error":{"code":42}}'])
async def test_malformed_error_keeps_safe_http_classification(body: bytes) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503, content=body))
    async with ApiClient("http://api.test", transport=transport) as client:
        with pytest.raises(ApiError) as caught:
            await client.health()
    assert caught.value.kind == ApiFailure.SERVER
    assert caught.value.error_code is None


@pytest.mark.anyio
async def test_compatible_with_current_fastapi_health_contract() -> None:
    # ASGI only; dependency override prevents opening PostgreSQL or running lifespan.
    application = create_app(
        Settings(_env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(24)))
    )
    session = Mock(spec=Session)
    application.dependency_overrides[get_session] = lambda: session
    async with ApiClient(
        "http://api.test", transport=httpx.ASGITransport(app=application)
    ) as client:
        assert (await client.health()).database == "ok"
        session.execute.side_effect = OperationalError("SELECT 1", {}, Exception())
        with pytest.raises(ApiError) as caught:
            await client.health()
    assert caught.value.kind == ApiFailure.SERVER
    assert caught.value.error_code == "database_unavailable"
    assert caught.value.request_id
