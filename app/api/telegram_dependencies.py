"""Internal service credential is verified before considering any Telegram actor."""

import re
import secrets
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_settings
from app.config import Settings
from app.core.errors import ApiError
from app.db import get_session
from app.models import User

service_header = APIKeyHeader(name="X-Bot-Service-Token", auto_error=False)


def get_telegram_actor(
    request: Request,
    credential: Annotated[str | None, Depends(service_header)],
    settings: Annotated[Settings, Depends(get_settings)],
    raw: Annotated[
        str,
        Header(
            alias="X-Telegram-ID",
            description="Positive Telegram sender ID from the trusted bot update",
        ),
    ] = "",
) -> int:
    if "Authorization" in request.headers:
        raise ApiError(400, "ambiguous_actor", "Use one authentication channel")
    expected = settings.require_bot_service_token()
    if (
        len(request.headers.getlist("X-Bot-Service-Token")) != 1
        or credential is None
        or not secrets.compare_digest(
            credential.encode("utf-8"), expected.encode("utf-8")
        )
    ):
        raise ApiError(
            401,
            "invalid_service_token",
            "Invalid or missing service credential",
            auth_scheme="BotService",
        )
    if len(request.headers.getlist("X-Telegram-ID")) != 1:
        raise ApiError(400, "validation_error", "Invalid Telegram actor")
    if re.fullmatch(r"[1-9][0-9]{0,18}", raw) is None or int(raw) > 2**63 - 1:
        raise ApiError(400, "validation_error", "Invalid Telegram actor")
    return int(raw)


def get_bot_user(
    telegram_id: Annotated[int, Depends(get_telegram_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    user = session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise ApiError(404, "telegram_profile_not_found", "Telegram profile not found")
    return user
