"""One private delivery attempt after a server claim; never retries finance writes."""

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.api_client import ApiError, BotApi
from skinulis_logging import Event, emit

DELIVERY_TIMEOUT = 5
NOTICE = (
    "Для вас могла появиться заявка на подтверждение перевода. "
    "Откройте /start → Ожидают подтверждения и проверьте актуальный статус. "
    "Подтверждайте только реально полученные деньги. Бот не переводит деньги."
)


async def notify_receiver(
    bot: Bot, api: BotApi, actor: int, settlement_id: int
) -> None:
    """Only call after acknowledged create/recovery, with the trusted sender actor.

    A committed claim is consumed even if its response or delivery is lost.
    Recipient identity comes exclusively from this internal server operation.
    """
    try:
        claim = await api.claim_settlement_notification(actor, settlement_id)
    except ApiError:
        emit(Event.NOTIFICATION_CLAIM_FAILED)
        return
    if claim is None:
        return
    try:
        async with asyncio.timeout(DELIVERY_TIMEOUT):
            await bot.send_message(
                chat_id=claim.recipient_telegram_id, text=NOTICE, parse_mode=None
            )
    except (TelegramAPIError, TimeoutError, OSError):
        # Never log the Telegram exception: it can contain identity or credentials.
        emit(Event.NOTIFICATION_DELIVERY_FAILED)
