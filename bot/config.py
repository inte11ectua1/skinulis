"""Bot-only configuration; secrets never appear in repr or validation errors."""

import re

from aiogram.utils.token import TokenValidationError, validate_token
from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    telegram_bot_token: SecretStr = Field(repr=False)
    bot_service_token: SecretStr = Field(repr=False)
    api_base_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:8000"), repr=False
    )

    @field_validator("telegram_bot_token")
    @classmethod
    def check_token(cls, value: SecretStr) -> SecretStr:
        try:
            validate_token(value.get_secret_value())
        except TokenValidationError:
            raise ValueError("Set a valid TELEGRAM_BOT_TOKEN") from None
        return value

    @field_validator("api_base_url")
    @classmethod
    def check_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError(
                "API_BASE_URL must not contain credentials, query or fragment"
            )
        return value

    @field_validator("bot_service_token")
    @classmethod
    def check_service_token(cls, value: SecretStr) -> SecretStr:
        if re.fullmatch(r"[A-Za-z0-9_-]{43,128}", value.get_secret_value()) is None:
            raise ValueError(
                "Set a separate URL-safe BOT_SERVICE_TOKEN (43–128 characters)"
            )
        return value
