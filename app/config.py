"""Настройки: секреты не попадают в repr и ошибки валидации."""

import re
import secrets
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr | None = Field(default=None, repr=False)
    postgres_host: str = Field(default="localhost", min_length=1)
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="skinulis", min_length=1)
    postgres_user: str = Field(default="skinulis", min_length=1)
    postgres_password: SecretStr | None = Field(default=None, repr=False)
    bot_service_token: SecretStr | None = Field(default=None, repr=False)
    jwt_secret_key: SecretStr | None = Field(default=None, repr=False)
    jwt_access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)

    @field_validator(
        "database_url",
        "postgres_password",
        "app_commit_sha",
        "jwt_secret_key",
        "bot_service_token",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_database(self) -> "Settings":
        if self.database_url is None:
            if (
                self.postgres_password is None
                or not self.postgres_password.get_secret_value()
            ):
                raise ValueError("Set DATABASE_URL or a non-empty POSTGRES_PASSWORD")
        else:
            try:
                url = make_url(self.database_url.get_secret_value())
                valid = (
                    url.drivername == "postgresql+psycopg"
                    and url.host
                    and url.username
                    and url.password
                    and url.database
                )
                _ = url.port
            except (ArgumentError, ValueError):
                valid = False
            if not valid:
                raise ValueError(
                    "DATABASE_URL must be a complete postgresql+psycopg URL"
                ) from None
        return self

    def get_database_url(self) -> URL:
        if self.database_url is not None:
            return make_url(self.database_url.get_secret_value())
        assert self.postgres_password is not None  # validated above
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    def require_jwt_secret(self) -> str:
        # Only API startup/auth needs JWT; migration-only Settings stays independent.
        value = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if len(value.encode("utf-8")) < 32:
            raise ValueError(
                "Set JWT_SECRET_KEY to a random secret of at least 32 bytes"
            )
        return value

    def require_bot_service_token(self) -> str:
        value = (
            self.bot_service_token.get_secret_value() if self.bot_service_token else ""
        )
        if re.fullmatch(r"[A-Za-z0-9_-]{43,128}", value) is None:
            raise ValueError(
                "Set BOT_SERVICE_TOKEN to a separate random URL-safe secret (43–128 characters)"
            )
        # A Telegram Bot API token contains ':' and cannot match the format above.
        other_secrets = [
            self.require_jwt_secret(),
            self.get_database_url().password or "",
        ]
        if any(
            secrets.compare_digest(value.encode(), other.encode())
            for other in other_secrets
        ):
            raise ValueError(
                "BOT_SERVICE_TOKEN must differ from JWT and database secrets"
            )
        return value
