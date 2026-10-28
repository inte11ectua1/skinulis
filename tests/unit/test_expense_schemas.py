"""Approved JSON union, exact input validation and documented API surface."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.expenses import (
    CreateInput,
    ExpenseMutation,
    ExpenseProfile,
    PreviewInput,
    PreviewProfile,
    QueryVersion,
    UpdateInput,
)


def equal() -> dict[str, Any]:
    return dict(
        title=" Обед ",
        split_mode="equal",
        amount="100.00",
        participants=[10, 2, 5],
        client_request_id=str(uuid4()),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", 100),
        ("amount", True),
        ("amount", None),
        ("amount", "0.00"),
        ("amount", "1000000.01"),
        ("amount", "1.0"),
        ("amount", "+1.00"),
        ("amount", "01.00"),
        ("amount", "1.00\n"),
        ("amount", "١.٠٠"),
        ("amount", "9" * 1000 + ".00"),
        ("participants", []),
        ("participants", [2, 2]),
        ("participants", [True]),
        ("participants", [2.0]),
        ("participants", ["2"]),
        ("participants", [0]),
        ("participants", [2**63]),
        ("participants", list(range(1, 32))),
        ("title", " "),
        ("title", "👩\u200d💻"),
        ("title", "a" * 121),
        ("split_mode", "by_items"),
        ("client_request_id", "bad"),
        ("payer_id", 2),
        ("author_id", 2),
        ("telegram_id", 2),
        ("group_id", 2),
        ("items", []),
        ("shares", []),
        ("expected_version", 1),
    ],
)
def test_create_rejects_invalid_or_spoofed_fields(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter[CreateInput](CreateInput).validate_python(equal() | {field: value})


def test_normalized_equal_and_custom_share_boundary() -> None:
    value = TypeAdapter[CreateInput](CreateInput).validate_python(
        equal() | {"title": " e\u0301 "}
    )
    assert value.title == "é"
    custom: dict[str, Any] = dict(
        title="Обед",
        split_mode="custom",
        amount="100.00",
        client_request_id=str(uuid4()),
        shares=[
            dict(user_id=2, amount="0.00"),
            dict(user_id=5, amount="40.00"),
            dict(user_id=10, amount="60.00"),
        ],
    )
    assert (
        TypeAdapter[CreateInput](CreateInput).validate_python(custom).draft().amount
        == "100.00"
    )
    for amount in ("59.99", "60.01", "-0.01"):
        invalid = deepcopy(custom)
        invalid["shares"][2]["amount"] = amount
        with pytest.raises(ValidationError):
            TypeAdapter[CreateInput](CreateInput).validate_python(invalid)
    overrides_list: tuple[dict[str, Any], ...] = (
        {"participants": []},
        {
            "shares": [
                {"user_id": 2, "amount": "40.00"},
                {"user_id": 2, "amount": "60.00"},
            ]
        },
        {"shares": [{"user_id": 2}]},
    )
    for overrides in overrides_list:
        with pytest.raises(ValidationError):
            TypeAdapter[CreateInput](CreateInput).validate_python(custom | overrides)


@pytest.mark.parametrize("version", [None, 0, -1, True, 1.0, "1", 2**63])
def test_put_requires_strict_positive_bigint_version(version: Any) -> None:
    payload = equal()
    payload.pop("client_request_id")
    with pytest.raises(ValidationError):
        TypeAdapter[UpdateInput](UpdateInput).validate_python(
            payload | {"expected_version": version}
        )


def test_preview_has_no_request_key_or_version_and_put_has_no_request_key() -> None:
    payload = equal()
    payload.pop("client_request_id")
    TypeAdapter[PreviewInput](PreviewInput).validate_python(payload)
    TypeAdapter[UpdateInput](UpdateInput).validate_python(
        payload | {"expected_version": 1}
    )
    for extra in ({"client_request_id": str(uuid4())}, {"expected_version": 1}):
        with pytest.raises(ValidationError):
            TypeAdapter[PreviewInput](PreviewInput).validate_python(payload | extra)
    with pytest.raises(ValidationError):
        TypeAdapter[UpdateInput](UpdateInput).validate_python(
            equal() | {"expected_version": 1}
        )


@pytest.mark.parametrize(
    "value", ["0", "-1", "1.0", "true", "+1", "01", " 1", "9" * 100]
)
def test_delete_query_version_is_a_canonical_positive_integer(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter[QueryVersion](QueryVersion).validate_python(value)


def test_delete_query_version_accepts_integer_text() -> None:
    assert TypeAdapter[QueryVersion](QueryVersion).validate_python("1") == 1


def test_published_client_fixtures_match_implemented_typed_contract() -> None:
    path = (
        Path(__file__).resolve().parents[2] / "docs/finance/fixtures/O-04_EXPENSES.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("equal_create", "custom_create"):
        TypeAdapter[CreateInput](CreateInput).validate_python(data[key])
    TypeAdapter[PreviewInput](PreviewInput).validate_python(data["preview_request"])
    TypeAdapter[UpdateInput](UpdateInput).validate_python(data["put_request"])
    ExpenseProfile.model_validate(data["equal_read"])
    PreviewProfile.model_validate(data["preview_response"])
    for key in ("create_response", "put_response", "delete_response"):
        ExpenseMutation.model_validate(data[key])
