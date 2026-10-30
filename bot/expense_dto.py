"""O-04/O-05 wire DTOs. Shape validation only; money is calculated by the API."""

import unicodedata
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, TypeAdapter, field_validator, model_validator

from bot.dto import EntityId, WireModel

Money = Annotated[
    str, Field(strict=True, max_length=10, pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")
]
Version = EntityId


def title_input(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(value) <= 120 or any(
        unicodedata.category(c).startswith("C") for c in value
    ):
        raise ValueError("Use 1–120 visible characters")
    return value


def money_input(value: str, *, zero: bool = False) -> str:
    value = TypeAdapter(Money).validate_python(value)
    if not zero and value == "0.00":
        raise ValueError("Use a positive amount")
    return value


class ExpenseWire(WireModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class Share(ExpenseWire):
    user_id: EntityId
    amount: Money


class NamedAmount(ExpenseWire):
    title: str
    amount: Money

    _title = field_validator("title")(title_input)

    @field_validator("amount")
    @classmethod
    def positive(cls, value: str) -> str:
        return money_input(value)


class ReceiptItem(NamedAmount):
    participants: list[EntityId] = Field(min_length=1, max_length=30)

    @field_validator("participants")
    @classmethod
    def unique(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Select each participant once")
        return value


class EqualDraft(ReceiptItem):
    split_mode: Literal["equal"]


class CustomDraft(NamedAmount):
    split_mode: Literal["custom"]
    shares: list[Share] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({s.user_id for s in self.shares}) != len(self.shares):
            raise ValueError("Select each participant once")
        # Exact sum, range and membership are intentionally server checks.
        return self


class ReceiptDraft(ExpenseWire):
    title: str
    split_mode: Literal["by_items"]
    items: list[ReceiptItem] = Field(min_length=1, max_length=50)

    _title = field_validator("title")(title_input)


type ExpenseDraft = Annotated[
    EqualDraft | CustomDraft | ReceiptDraft, Field(discriminator="split_mode")
]
DRAFT: TypeAdapter[ExpenseDraft] = TypeAdapter(ExpenseDraft)


class ItemProfile(ExpenseWire):
    position: int = Field(ge=1, le=50)
    title: str
    amount: Money
    shares: list[Share]


class PreviewFields(ExpenseWire):
    group_id: EntityId
    payer_id: EntityId
    title: str
    amount: Money
    shares: list[Share]


class SplitPreview(PreviewFields):
    split_mode: Literal["equal", "custom"]


class ReceiptPreview(PreviewFields):
    split_mode: Literal["by_items"]
    items: list[ItemProfile] = Field(min_length=1, max_length=50)


type ExpensePreview = Annotated[
    SplitPreview | ReceiptPreview, Field(discriminator="split_mode")
]
PREVIEW: TypeAdapter[ExpensePreview] = TypeAdapter(ExpensePreview)


class ProfileFields(PreviewFields):
    id: EntityId
    client_request_id: UUID
    created_at: datetime
    deleted_at: datetime | None
    version: Version


class SplitExpense(ProfileFields):
    split_mode: Literal["equal", "custom"]


class ReceiptExpense(ProfileFields):
    split_mode: Literal["by_items"]
    items: list[ItemProfile] = Field(min_length=1, max_length=50)


type ExpenseProfile = Annotated[
    SplitExpense | ReceiptExpense, Field(discriminator="split_mode")
]
EXPENSE: TypeAdapter[ExpenseProfile] = TypeAdapter(ExpenseProfile)


class Balance(ExpenseWire):
    user_id: EntityId
    balance: Annotated[str, Field(pattern=r"^-?(0|[1-9][0-9]*)\.[0-9]{2}$")]


class ExpenseMutation(ExpenseWire):
    expense: ExpenseProfile
    balances: list[Balance] | None


def draft_from_profile(value: ExpenseProfile) -> ExpenseDraft:
    """Recover historical selections including zeros; never infer a new split."""
    common = {"title": value.title, "split_mode": value.split_mode}
    if isinstance(value, ReceiptExpense):
        return DRAFT.validate_python(
            common
            | {
                "items": [
                    {
                        "title": i.title,
                        "amount": i.amount,
                        "participants": [s.user_id for s in i.shares],
                    }
                    for i in value.items
                ]
            }
        )
    if value.split_mode == "equal":
        return EqualDraft(
            title=value.title,
            split_mode="equal",
            amount=value.amount,
            participants=[s.user_id for s in value.shares],
        )
    return CustomDraft(
        title=value.title,
        split_mode="custom",
        amount=value.amount,
        shares=value.shares,
    )
