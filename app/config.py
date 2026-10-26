"""Настройки: секреты не попадают в repr и ошибки валидации."""

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

    @field_validator(
        "database_url", "postgres_password", "app_commit_sha", mode="before"
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
