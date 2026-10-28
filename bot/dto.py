"""Client DTOs for the approved T-05/T-06 wire schemas; no DB imports."""

import re
import unicodedata
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

EntityId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]


class WireModel(BaseModel):
    model_config = ConfigDict(strict=True, hide_input_in_errors=True)


class UserProfile(WireModel):
    id: EntityId
    email: str | None = Field(repr=False)
    telegram_id: EntityId | None = Field(repr=False)
    created_at: datetime


class GroupProfile(WireModel):
    id: EntityId
    name: str
    owner_id: EntityId
    created_at: datetime


class MemberProfile(WireModel):
    user_id: EntityId
    joined_at: datetime
    is_owner: bool


class Page[T](WireModel):
    items: list[T]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class InviteProfile(WireModel):
    id: EntityId
    group_id: EntityId
    client_request_id: UUID
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    revoked_at: datetime | None


class InviteIssued(InviteProfile):
    token: SecretStr | None = Field(repr=False)


class GroupDraft(WireModel):
    """Only presentation/input normalization, identical to T-06 GroupCreate."""

    name: str
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


def valid_capability(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is not None
