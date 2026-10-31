import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.settlements import build_router
from app.core.errors import ApiError
from app.schemas.groups import Page
from app.schemas.settlements import (
    SettlementCreate,
    SettlementMutation,
    SettlementProfile,
)
from app.services.settlements import (
    Action,
    Intent,
    check_balance,
    normalize_intent,
    require_role,
)

KEY = "00000000-0000-4000-8000-000000000001"


@pytest.mark.parametrize(
    "amount", ["0.01", "500.00", "1500000.00", "92233720368547758.07"]
)
def test_exact_normalized_intent(amount: str) -> None:
    draft = SettlementCreate(receiver_id=10, amount=amount, client_request_id=UUID(KEY))
    intent = normalize_intent(1, 20, draft)
    assert (intent.group_id, intent.sender_id, intent.receiver_id) == (1, 20, 10)
    assert type(intent.amount_kopecks) is int
    assert intent == normalize_intent(
        1, 20, SettlementCreate.model_validate_json(draft.model_dump_json())
    )


@pytest.mark.parametrize(
    "amount",
    [
        "0.00",
        "-0.01",
        "+1.00",
        "01.00",
        " 1.00",
        "1.00\n",
        "1,00",
        "1.0",
        "1.000",
        "1e2",
        "１.00",
        "1.٠٠",
        "92233720368547758.08",
        "9" * 500,
        1,
        1.0,
        True,
        None,
    ],
)
def test_invalid_money(amount: Any) -> None:
    with pytest.raises(ValidationError):
        SettlementCreate.model_validate(
            dict(receiver_id=10, amount=amount, client_request_id=KEY)
        )


@pytest.mark.parametrize("receiver", [0, -1, 2**63, True, "10", 10.0, None])
def test_strict_receiver(receiver: Any) -> None:
    with pytest.raises(ValidationError):
        SettlementCreate.model_validate(
            dict(receiver_id=receiver, amount="1.00", client_request_id=KEY)
        )


@pytest.mark.parametrize(
    "field", ["sender_id", "group_id", "status", "resolved_at", "id", "telegram_id"]
)
def test_client_cannot_supply_actor_or_server_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        SettlementCreate.model_validate(
            dict(receiver_id=10, amount="1.00", client_request_id=KEY) | {field: 10}
        )


@pytest.mark.parametrize(
    "action,allowed,code",
    [
        ("confirm", 10, "settlement_receiver_required"),
        ("reject", 10, "settlement_receiver_required"),
        ("cancel", 20, "settlement_sender_required"),
    ],
)
def test_roles(action: Action, allowed: int, code: str) -> None:
    require_role(action, allowed, 20, 10)
    for actor in {10, 20, 30} - {allowed}:
        with pytest.raises(ApiError) as error:
            require_role(action, actor, 20, 10)
        assert (error.value.status, error.value.code) == (403, code)


@pytest.mark.parametrize(
    "sender,receiver,amount,allowed",
    [
        (-140000, 220000, 50000, True),
        (-140000, 220000, 140000, True),
        (-140000, 220000, 140001, False),
        (-140000, 100, 101, False),
        (0, 100, 1, False),
        (100, -100, 1, False),
        (-100, 0, 1, False),
        (-(10**30), 10**30, 2**63 - 1, True),
    ],
)
def test_fresh_balance_limit(
    sender: int, receiver: int, amount: int, allowed: bool
) -> None:
    vector = {10: receiver, 20: sender}
    intent = Intent(1, 20, 10, amount)
    if allowed:
        check_balance(vector, intent)
    else:
        with pytest.raises(ApiError) as error:
            check_balance(vector, intent)
        assert (error.value.status, error.value.code) == (
            409,
            "settlement_balance_conflict",
        )


def test_uuid_and_typed_fixtures_openapi() -> None:
    with pytest.raises(ValidationError):
        SettlementCreate(receiver_id=10, amount="1.00", client_request_id="bad")
    data = json.loads(
        Path("docs/finance/fixtures/O-07_SETTLEMENTS.json").read_text(encoding="utf-8")
    )
    for key in ("create", "confirmed", "rejected", "cancelled"):
        assert (
            SettlementMutation.model_validate(data[key]).model_dump(mode="json")
            == data[key]
        )
    assert (
        Page[SettlementProfile].model_validate(data["page"]).model_dump(mode="json")
        == data["page"]
    )
    application = FastAPI()
    application.include_router(build_router())
    application.include_router(build_router(internal=True))
    schema = application.openapi()
    assert len(schema["paths"]) == 8
    for prefix in ("", "/internal"):
        assert {"get", "post"} <= set(
            schema["paths"][prefix + "/groups/{group_id}/settlements"]
        )
        for action in ("confirm", "reject", "cancel"):
            assert (
                "post"
                in schema["paths"][prefix + "/settlements/{settlement_id}/" + action]
            )
