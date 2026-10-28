"""Expense DTOs approved by T-07: issue #36 comment 6469818682."""

import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.auth import UserId
from app.schemas.timestamps import UTCDateTime
from app.services.expenses import (
    CustomExpense,
    EqualExpense,
    normalize_title,
    prepare_expense,
)

# A valid single expense/custom share cannot exceed 1000000.00 RUB (10 chars).
# This bound is local to expense inputs, never applied to balances/settlements.
Money = Annotated[
    str, Field(strict=True, max_length=10, pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")
]
Version = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]


def _query_integer(value: object) -> object:
    if type(value) is int:
        return value
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,18}", value) is None:
        raise ValueError("Use a positive integer version")
    return value


QueryVersion = Annotated[
    int, BeforeValidator(_query_integer), Field(ge=1, le=2**63 - 1)
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    title: str = Field(strict=True, examples=["Обед"])
    amount: Money = Field(examples=["100.00"])

    @field_validator("title")
    @classmethod
    def title_policy(cls, value: str) -> str:
        return normalize_title(value)


class EqualInput(Input):
    split_mode: Literal["equal"]
    participants: list[UserId] = Field(min_length=1, max_length=30)

    def draft(self) -> EqualExpense:
        return EqualExpense(self.title, self.amount, tuple(self.participants))

    @model_validator(mode="after")
    def exact_input(self) -> Self:
        prepare_expense(self.draft(), self.participants)
        return self


class CustomShare(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    user_id: UserId
    amount: Money


class CustomInput(Input):
    split_mode: Literal["custom"]
    shares: list[CustomShare] = Field(min_length=1, max_length=30)

    def draft(self) -> CustomExpense:
        return CustomExpense(
            self.title,
            self.amount,
            tuple((row.user_id, row.amount) for row in self.shares),
        )

    @model_validator(mode="after")
    def exact_input(self) -> Self:
        prepare_expense(self.draft(), [row.user_id for row in self.shares])
        return self


class EqualCreate(EqualInput):
    client_request_id: UUID


class CustomCreate(CustomInput):
    client_request_id: UUID


class EqualUpdate(EqualInput):
    expected_version: Version


class CustomUpdate(CustomInput):
    expected_version: Version


type PreviewInput = Annotated[
    EqualInput | CustomInput, Field(discriminator="split_mode")
]
type CreateInput = Annotated[
    EqualCreate | CustomCreate, Field(discriminator="split_mode")
]
type UpdateInput = Annotated[
    EqualUpdate | CustomUpdate, Field(discriminator="split_mode")
]


class ShareProfile(BaseModel):
    user_id: UserId
    amount: str


class PreviewProfile(BaseModel):
    group_id: UserId
    payer_id: UserId
    split_mode: Literal["equal", "custom"]
    title: str
    amount: str
    shares: list[ShareProfile]


class ExpenseProfile(BaseModel):
    id: UserId
    group_id: UserId
    payer_id: UserId
    client_request_id: UUID
    split_mode: Literal["equal", "custom", "by_items"]
    title: str
    amount: str
    shares: list[ShareProfile]
    created_at: UTCDateTime
    deleted_at: UTCDateTime | None
    version: Version


class BalanceProfile(BaseModel):
    user_id: UserId
    balance: str


class ExpenseMutation(BaseModel):
    expense: ExpenseProfile
    balances: list[BalanceProfile] | None
