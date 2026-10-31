"""Accepted T-08 settlement wire contract; no client-controlled sender or status."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import UserId
from app.schemas.groups import Input
from app.schemas.timestamps import UTCDateTime
from app.services.money import parse_money

SettlementStatus = Literal["pending", "confirmed", "rejected", "cancelled"]
Direction = Literal["incoming", "outgoing", "all"]


class NotificationClaim(BaseModel):
    """Internal-only permission; never embed in a financial/member profile."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"recipient_telegram_id": 123456789}]},
    )
    recipient_telegram_id: UserId


SettlementAmount = Annotated[
    str, Field(strict=True, max_length=20, pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")
]


class SettlementCreate(Input):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "receiver_id": 10,
                    "amount": "500.00",
                    "client_request_id": "00000000-0000-4000-8000-000000000001",
                }
            ]
        }
    )
    receiver_id: UserId
    amount: SettlementAmount
    client_request_id: UUID

    @field_validator("amount")
    @classmethod
    def valid_amount(cls, value: str) -> str:
        parse_money(value, minimum=1, maximum=2**63 - 1)
        return value


class SettlementProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UserId
    group_id: UserId
    sender_id: UserId
    receiver_id: UserId
    amount: SettlementAmount
    status: SettlementStatus
    client_request_id: UUID
    created_at: UTCDateTime
    resolved_at: UTCDateTime | None


class SettlementMutation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "settlement": {
                        "id": 123,
                        "group_id": 10,
                        "sender_id": 20,
                        "receiver_id": 10,
                        "amount": "500.00",
                        "status": "pending",
                        "client_request_id": "00000000-0000-4000-8000-000000000001",
                        "created_at": "2026-10-30T12:00:00Z",
                        "resolved_at": None,
                    }
                }
            ]
        },
    )
    settlement: SettlementProfile
