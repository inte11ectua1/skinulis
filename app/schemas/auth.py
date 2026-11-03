"""Proposed T-05 public DTOs; bot-service/onboarding remain T-06."""

import unicodedata
from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.timestamps import UTCDateTime

UserId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    email: str = Field(min_length=3, max_length=254, examples=["alice@example.com"])
    password: SecretStr = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        try:
            address = validate_email(
                value.strip(), check_deliverability=False, allow_smtputf8=False
            ).ascii_email
        except EmailNotValidError:
            raise ValueError("Invalid email address") from None
        assert address is not None
        return address.lower()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.strip() or any(unicodedata.category(c).startswith("C") for c in raw):
            raise ValueError("Use a non-blank password without control characters")
        return value


class RegisterInput(LoginInput):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "alice@example.com",
                    "password": "<15-128-character-passphrase>",
                }
            ]
        }
    )
    password: SecretStr = Field(min_length=15, max_length=128, repr=False)


class UserProfile(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "email": "alice@example.com",
                    "display_name": "Алиса",
                    "telegram_id": None,
                    "created_at": "2026-10-27T00:00:00Z",
                }
            ]
        },
    )

    id: UserId
    display_name: str | None = None
    email: str | None
    telegram_id: UserId | None
    created_at: UTCDateTime


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "<access-token>",
                    "token_type": "bearer",
                    "expires_in": 900,
                }
            ]
        }
    )
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={"examples": [{"display_name": "Тимур"}]},
    )
    display_name: str = Field(strict=True)

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value).strip()
        if not 1 <= len(value) <= 64 or any(
            unicodedata.category(c).startswith("C") for c in value
        ):
            raise ValueError("Use 1–64 visible characters without control characters")
        return value


class BootstrapInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        json_schema_extra={"examples": [{"display_name": "Тимур"}, {}]},
    )
    display_name: str | None = Field(default=None, strict=True)

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return ProfileUpdate.normalize_name(value) if value is not None else None
