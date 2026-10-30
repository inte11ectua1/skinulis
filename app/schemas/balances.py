"""Approved T-08 O-06 responses; amounts have no single-expense cap."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import UserId
from app.schemas.expenses import BalanceProfile


class BalancesResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "group_id": 10,
                    "balances": [
                        {"user_id": 10, "balance": "2200.00"},
                        {"user_id": 20, "balance": "-1400.00"},
                        {"user_id": 30, "balance": "-800.00"},
                    ],
                }
            ]
        },
    )
    group_id: UserId
    balances: list[BalanceProfile]


class TransferProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_id: UserId
    receiver_id: UserId
    amount: Annotated[str, Field(strict=True, pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")]


class PlanResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "group_id": 10,
                    "transfers": [
                        {"sender_id": 20, "receiver_id": 10, "amount": "1400.00"},
                        {"sender_id": 30, "receiver_id": 10, "amount": "800.00"},
                    ],
                }
            ]
        },
    )
    group_id: UserId
    transfers: list[TransferProfile]
