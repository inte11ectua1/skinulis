"""Bounded in-process delivery deduplication; no user data or secrets retained."""

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from skinulis_logging import Event, emit, request_context


class SafeTelegramLogs(logging.Filter):
    """aiogram can log bot identity and raw exception args outside router errors."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return False
        record.msg = Event.TELEGRAM
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def protect_telegram_logs() -> None:
    for name in ("dispatcher", "event", "middlewares", "webhook", "scene"):
        logger = logging.getLogger("aiogram." + name)
        if not any(isinstance(item, SafeTelegramLogs) for item in logger.filters):
            logger.addFilter(SafeTelegramLogs())


class DeliveredUpdates(BaseMiddleware):
    def __init__(self) -> None:
        self._seen: OrderedDict[int, None] = OrderedDict()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            if event.update_id in self._seen:
                return None
            # Mark before await. Uncertain writes must be recovered via the UI.
            self._seen[event.update_id] = None
            if len(self._seen) > 4096:
                self._seen.popitem(last=False)
        with request_context():
            try:
                return await handler(event, data)
            except Exception:
                emit(Event.BOT_UPDATE_FAILED, level=logging.ERROR)
                raise
