"""Run one polling process with `uv run python -m bot.main`."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from pydantic import ValidationError

from bot.api_client import ApiClient
from bot.config import BotSettings
from bot.handlers import create_router
from bot.middleware import DeliveredUpdates, protect_telegram_logs
from skinulis_logging import Event, Fields, Outcome, configure_logging, emit


def telegram_outcome(error: BaseException) -> Outcome:
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return Outcome.TIMEOUT
    if isinstance(error, TelegramRetryAfter):
        return Outcome.RETRY
    if isinstance(error, TelegramNetworkError):
        return Outcome.NETWORK
    if isinstance(error, TelegramAPIError):
        return Outcome.TELEGRAM
    return Outcome.UNEXPECTED


def create_dispatcher() -> Dispatcher:
    protect_telegram_logs()
    dispatcher = Dispatcher(
        storage=MemoryStorage(), events_isolation=SimpleEventIsolation()
    )
    dispatcher.update.outer_middleware(DeliveredUpdates())
    dispatcher.include_router(create_router())
    return dispatcher


async def run(settings: BotSettings) -> None:
    async with ApiClient(
        str(settings.api_base_url), service_token=settings.bot_service_token
    ) as api:
        async with Bot(
            token=settings.telegram_bot_token.get_secret_value()
        ).context() as telegram:
            dispatcher = create_dispatcher()
            emit(Event.BOT_STARTED)
            try:
                await dispatcher.start_polling(
                    telegram,
                    api=api,
                    allowed_updates=dispatcher.resolve_used_update_types(),
                    close_bot_session=False,
                    handle_as_tasks=False,
                )
            finally:
                # Also covers startup failure/cancellation before aiogram's shutdown.
                # MemoryStorage and SimpleEventIsolation close are idempotent.
                await dispatcher.fsm.close()
                emit(Event.BOT_STOPPED)


def main() -> int:
    configure_logging("bot")
    try:
        settings = BotSettings()
    except ValidationError:
        emit(Event.BOT_CONFIG_INVALID, level=logging.ERROR)
        return 2
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        # Underlying Telegram/network exceptions may contain credentials or URLs.
        emit(
            Event.BOT_FAILED,
            level=logging.ERROR,
            fields=Fields(outcome=telegram_outcome(error)),
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
