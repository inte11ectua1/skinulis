"""Run one polling process with `uv run python -m bot.main`."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from pydantic import ValidationError

from bot.api_client import ApiClient
from bot.config import BotSettings
from bot.handlers import create_router

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(
        storage=MemoryStorage(), events_isolation=SimpleEventIsolation()
    )
    dispatcher.include_router(create_router())
    return dispatcher


async def run(settings: BotSettings) -> None:
    async with ApiClient(str(settings.api_base_url)) as api:
        async with Bot(
            token=settings.telegram_bot_token.get_secret_value()
        ).context() as telegram:
            dispatcher = create_dispatcher()
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


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    try:
        settings = BotSettings()
    except ValidationError:
        logger.error("Проверьте TELEGRAM_BOT_TOKEN и API_BASE_URL в окружении или .env")
        return 2
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        return 0
    except Exception:
        # Underlying Telegram/network exceptions may contain credentials or URLs.
        logger.error("Не удалось запустить или продолжить работу бота")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
