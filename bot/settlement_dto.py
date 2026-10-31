"""Accepted T-08/O-06/O-07 wire shapes; no financial calculations."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from bot.dto import EntityId, WireModel
from bot.expense_dto import Balance

type SettlementStatus = Literal["pending", "confirmed", "rejected", "cancelled"]
type Direction = Literal["incoming", "outgoing", "all"]
type Transition = Literal["confirm", "reject", "cancel"]
SettlementAmount = Annotated[
    str, Field(strict=True, max_length=20, pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")
]


class SettlementWire(WireModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class NotificationClaim(SettlementWire):
    recipient_telegram_id: EntityId = Field(repr=False)


class Balances(SettlementWire):
    group_id: EntityId
    balances: list[Balance]


class Transfer(SettlementWire):
    sender_id: EntityId
    receiver_id: EntityId
    amount: Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")]


class Plan(SettlementWire):
    group_id: EntityId
    transfers: list[Transfer]


def amount_input(value: str) -> str:
    value = TypeAdapter(SettlementAmount).validate_python(value)
    if value == "0.00":
        raise ValueError("Enter a positive canonical RUB string")
    # No expense cap, maximum/debt/min computation or rounding. API validates BIGINT.
    return value


class SettlementCreate(SettlementWire):
    receiver_id: EntityId
    amount: SettlementAmount
    client_request_id: UUID

    _positive = field_validator("amount")(amount_input)


class SettlementProfile(SettlementWire):
    id: EntityId
    group_id: EntityId
    sender_id: EntityId
    receiver_id: EntityId
    amount: SettlementAmount
    status: SettlementStatus
    client_request_id: UUID
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None

    @model_validator(mode="after")
    def state_timestamp(self) -> Self:
        if (self.status == "pending") != (self.resolved_at is None):
            raise ValueError("Inconsistent settlement status timestamp")
        return self


class SettlementMutation(SettlementWire):
    settlement: SettlementProfile
