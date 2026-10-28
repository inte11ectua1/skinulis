import asyncio
import secrets
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from pydantic import AnyHttpUrl, SecretStr, ValidationError

from bot import main as runtime
from bot.api_client import ApiClient
from bot.config import BotSettings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> BotSettings:
    generated = f"{secrets.randbelow(10**8) + 1}:{secrets.token_urlsafe(32)}"
    return BotSettings(
        _env_file=None,
        telegram_bot_token=SecretStr(generated),
        api_base_url=AnyHttpUrl("http://api.test:8000"),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["normal", "failure", "cancel"])
async def test_run_closes_api_and_telegram_sessions(
    settings: BotSettings, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    clients: list[ApiClient] = []
    session = AsyncMock(spec=BaseSession)

    def api_factory(base_url: str, *, service_token: SecretStr) -> ApiClient:
        assert service_token == settings.bot_service_token
        client = ApiClient(
            base_url,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"status": "ok", "database": "ok"})
            ),
        )
        clients.append(client)
        return client

    def telegram_factory(*, token: str) -> Bot:
        return Bot(token=token, session=session)

    failure: BaseException | None = None
    if outcome == "failure":
        failure = RuntimeError("startup failed")
    elif outcome == "cancel":
        failure = asyncio.CancelledError()
    poll = AsyncMock(side_effect=failure)
    monkeypatch.setattr(runtime, "ApiClient", api_factory)
    monkeypatch.setattr(runtime, "Bot", telegram_factory)
    monkeypatch.setattr(Dispatcher, "start_polling", poll)
    if failure is None:
        await runtime.run(settings)
    else:
        with pytest.raises(type(failure)):
            await runtime.run(settings)
    assert clients[0].is_closed
    session.close.assert_awaited_once()
    assert poll.await_args is not None
    assert poll.await_args.kwargs["api"] is clients[0]
    assert poll.await_args.kwargs["close_bot_session"] is False
    assert poll.await_args.kwargs["handle_as_tasks"] is False
    assert set(poll.await_args.kwargs["allowed_updates"]) == {
        "message",
        "callback_query",
    }


def test_configuration_from_environment_hides_secret(
    settings: BotSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = settings.telegram_bot_token.get_secret_value()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("API_BASE_URL", "http://api:8000")
    service_secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("BOT_SERVICE_TOKEN", service_secret)
    configured = BotSettings(_env_file=None)
    assert configured.telegram_bot_token.get_secret_value() == token
    assert str(configured.api_base_url) == "http://api:8000/"
    assert token not in repr(configured)
    assert service_secret not in repr(configured)
    assert configured.bot_service_token.get_secret_value() == service_secret


@pytest.mark.parametrize(
    "url",
    [
        "broken",
        "ftp://api.test",
        "http://api.test?key=hidden",
        "http://api.test/#fragment",
    ],
)
def test_invalid_api_configuration(settings: BotSettings, url: str) -> None:
    with pytest.raises(ValidationError):
        BotSettings(
            _env_file=None,
            telegram_bot_token=settings.telegram_bot_token,
            api_base_url=url,
        )


def test_url_credentials_are_not_leaked(settings: BotSettings) -> None:
    private = secrets.token_urlsafe(32)
    with pytest.raises(ValidationError) as caught:
        BotSettings(
            _env_file=None,
            telegram_bot_token=settings.telegram_bot_token,
            api_base_url=f"http://user:{private}@api.test",
        )
    assert private not in str(caught.value)


@pytest.mark.parametrize("token", ["", "invalid"])
def test_invalid_telegram_token(token: str) -> None:
    with pytest.raises(ValidationError):
        BotSettings(_env_file=None, telegram_bot_token=SecretStr(token))


def test_main_missing_token_fails_without_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Load real environment validation without the operator's .env or filesystem temp.
    monkeypatch.setattr(runtime, "BotSettings", lambda: BotSettings(_env_file=None))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)
    assert runtime.main() == 2
    assert "TELEGRAM_BOT_TOKEN" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize(
    "outcome,expected", [("normal", 0), ("interrupt", 0), ("failure", 1)]
)
def test_main_process_outcomes_do_not_log_secrets(
    settings: BotSettings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: str,
    expected: int,
) -> None:
    monkeypatch.setattr(runtime, "BotSettings", lambda: settings)
    private = settings.telegram_bot_token.get_secret_value()

    async def fake_run(configuration: BotSettings) -> None:
        if outcome == "interrupt":
            raise KeyboardInterrupt
        if outcome == "failure":
            raise RuntimeError(private)

    monkeypatch.setattr(runtime, "run", fake_run)
    assert runtime.main() == expected
    assert private not in caplog.text
    assert "Traceback" not in caplog.text
