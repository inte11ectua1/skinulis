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
    parsed = TypeAdapter[CreateInput](CreateInput).validate_python(custom)
    assert parsed.split_mode == "custom"
    assert parsed.draft().amount == "100.00"
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


def receipt_body() -> dict[str, Any]:
    return dict(
        title=" Ресторан ",
        split_mode="by_items",
        items=[
            dict(title=" e\u0301 ", amount="0.01", participants=[30, 10, 20]),
            dict(title="Сбор", amount="0.01", participants=[10, 20, 30]),
        ],
    )


@pytest.mark.parametrize(
    "field",
    [
        "amount",
        "participants",
        "shares",
        "payer_id",
        "author_id",
        "telegram_id",
        "group_id",
        "position",
        "item_id",
    ],
)
def test_receipt_forbids_root_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(PreviewInput).validate_python(receipt_body() | {field: 1})


@pytest.mark.parametrize(
    "field",
    [
        "position",
        "item_id",
        "group_id",
        "payer_id",
        "author_id",
        "telegram_id",
        "shares",
    ],
)
def test_receipt_forbids_nested_fields(field: str) -> None:
    body = receipt_body()
    body["items"][0][field] = 1
    with pytest.raises(ValidationError):
        TypeAdapter(PreviewInput).validate_python(body)


@pytest.mark.parametrize(
    "value", [[], [1, 1], [True], [1.0], ["1"], [0], [2**63], list(range(1, 32))]
)
def test_receipt_schema_strict_consumers(value: Any) -> None:
    body = receipt_body()
    body["items"][0]["participants"] = value
    with pytest.raises(ValidationError):
        TypeAdapter(PreviewInput).validate_python(body)


@pytest.mark.parametrize("count", [0, 51])
def test_receipt_schema_count_limits(count: int) -> None:
    body = receipt_body()
    body["items"] = [body["items"][0]] * count
    with pytest.raises(ValidationError):
        TypeAdapter(PreviewInput).validate_python(body)


@pytest.mark.parametrize(
    "amount", ["0.00", "1000000.01", "01.00", "1.0", "-1.00", 1, 1.0, True]
)
def test_receipt_schema_item_prices(amount: Any) -> None:
    body = receipt_body()
    body["items"][0]["amount"] = amount
    with pytest.raises(ValidationError):
        TypeAdapter(PreviewInput).validate_python(body)


def test_receipt_preview_create_update_shapes_and_total_limit() -> None:
    body = receipt_body()
    original = deepcopy(body)
    result = TypeAdapter[PreviewInput](PreviewInput).validate_python(body)
    assert result.split_mode == "by_items" and result.items[0].title == "é"
    assert body == original
    assert (
        TypeAdapter(CreateInput)
        .validate_python(body | dict(client_request_id=str(uuid4())))
        .draft()
        == result.draft()
    )
    assert (
        TypeAdapter(UpdateInput)
        .validate_python(body | dict(expected_version=1))
        .draft()
        == result.draft()
    )
    for key in ("client_request_id", "expected_version"):
        with pytest.raises(ValidationError):
            TypeAdapter(PreviewInput).validate_python(body | {key: 1})
    body["items"][0]["amount"] = "1000000.00"
    with pytest.raises(ValidationError):
        TypeAdapter(PreviewInput).validate_python(body)


def test_accepted_by_items_fixtures_and_openapi_union() -> None:
    from fastapi import FastAPI

    from app.api.expenses import build_router
    from app.schemas.expenses import ExpenseResponse, PreviewResponse

    fixture = Path("docs/finance/fixtures/O-05_BY_ITEMS.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    for key, model in [
        ("preview_request", PreviewInput),
        ("preview_response", PreviewResponse),
        ("create_request", CreateInput),
        ("create_response", ExpenseMutation),
        ("detail_response", ExpenseResponse),
        ("put_request", UpdateInput),
        ("penny_preview", PreviewResponse),
        ("original_post_replay", ExpenseMutation),
    ]:
        parsed: Any = TypeAdapter(model).validate_python(data[key])
        assert parsed is not None
    app = FastAPI()
    app.include_router(build_router())
    app.include_router(build_router(internal=True))
    document = app.openapi()
    for prefix in ("", "/internal"):
        for path, method in [
            (f"{prefix}/groups/{{group_id}}/expenses", "post"),
            (f"{prefix}/groups/{{group_id}}/expenses/preview", "post"),
            (f"{prefix}/expenses/{{expense_id}}", "put"),
        ]:
            schema = document["paths"][path][method]["requestBody"]["content"][
                "application/json"
            ]["schema"]
            assert set(schema["discriminator"]["mapping"]) == {
                "equal",
                "custom",
                "by_items",
            }
