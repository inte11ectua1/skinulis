"""T-06 DTOs approved by the technical lead in #22; no public JSON actor fields."""

import re
import unicodedata
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.auth import UserId


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EmptyInput(Input):
    pass


class GroupCreate(Input):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Поездка",
                    "client_request_id": "00000000-0000-4000-8000-000000000001",
                }
            ]
        }
    )
    name: str = Field(strict=True, examples=["Поездка"])
    client_request_id: UUID

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value).strip()
        if not 1 <= len(value) <= 120 or any(
            unicodedata.category(c).startswith("C") for c in value
        ):
            raise ValueError("Use 1–120 characters without control characters")
        return value


class RequestKey(Input):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"client_request_id": "00000000-0000-4000-8000-000000000002"}]
        }
    )
    client_request_id: UUID


class CapabilityInput(Input):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"token": "<43-character-invitation-secret>"}]}
    )
    token: SecretStr = Field(min_length=43, max_length=43, repr=False)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", value.get_secret_value()) is None:
            raise ValueError("Invalid secret format")
        return value


class LinkInput(Input):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"code": "<43-character-one-time-link-code>"}]}
    )
    code: SecretStr = Field(min_length=43, max_length=43, repr=False)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        return CapabilityInput.validate_token(value)


class GroupProfile(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "name": "Поездка",
                    "owner_id": 1,
                    "created_at": "2026-10-27T00:00:00Z",
                }
            ]
        },
    )
    id: UserId
    name: str
    owner_id: UserId
    created_at: datetime


class MemberProfile(BaseModel):
    user_id: UserId
    joined_at: datetime
    is_owner: bool


class Page[T](BaseModel):
    items: list[T]
    limit: int
    offset: int


class InviteProfile(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "group_id": 1,
                    "client_request_id": "00000000-0000-4000-8000-000000000002",
                    "created_at": "2026-10-27T00:00:00Z",
                    "expires_at": "2026-10-28T00:00:00Z",
                    "consumed_at": None,
                    "revoked_at": "2026-10-27T01:00:00Z",
                }
            ]
        },
    )
    id: UserId
    group_id: UserId
    client_request_id: UUID
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    revoked_at: datetime | None


class InviteIssued(InviteProfile):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "group_id": 1,
                    "client_request_id": "00000000-0000-4000-8000-000000000002",
                    "created_at": "2026-10-27T00:00:00Z",
                    "expires_at": "2026-10-28T00:00:00Z",
                    "consumed_at": None,
                    "revoked_at": None,
                    "token": "<issued-once-invitation-secret>",
                }
            ]
        },
    )
    token: str | None = Field(repr=False)


class LinkIssued(BaseModel):
    code: str = Field(repr=False)
    expires_at: datetime


# Path IDs are parsed by FastAPI and bounded to positive signed BIGINT.
PathId = Annotated[int, Field(gt=0, le=2**63 - 1)]
