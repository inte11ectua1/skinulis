import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.settlement_notifications import router
from app.api.settlements import build_router
from app.schemas.groups import MemberProfile
from app.schemas.settlements import NotificationClaim, SettlementProfile


@pytest.mark.parametrize("value", [1, 123456789, 2**63 - 1])
def test_recipient_id_is_strict_positive_bigint(value: int) -> None:
    assert NotificationClaim(recipient_telegram_id=value).recipient_telegram_id == value


@pytest.mark.parametrize("value", [0, -1, 2**63, True, "123", 1.0, None])
def test_invalid_recipient_binding(value: Any) -> None:
    with pytest.raises(ValidationError):
        NotificationClaim.model_validate(dict(recipient_telegram_id=value))


def test_internal_only_openapi_fixture_and_no_business_dto_leakage() -> None:
    application = FastAPI()
    application.include_router(build_router())
    application.include_router(build_router(internal=True))
    application.include_router(router)
    schema = application.openapi()
    path = "/internal/settlements/{settlement_id}/notification-claim"
    operation = schema["paths"][path]["post"]
    assert "requestBody" not in operation
    assert operation["security"] == [{"APIKeyHeader": []}]
    assert "content" not in operation["responses"]["204"]
    assert all(
        "notification-claim" not in p
        for p in schema["paths"]
        if not p.startswith("/internal/")
    )
    for model in (SettlementProfile, MemberProfile):
        assert not any(
            "telegram" in field or "notification" in field
            for field in model.model_fields
        )
    data = json.loads(
        Path("docs/finance/fixtures/O-07N_NOTIFICATION_CLAIM.json").read_text(
            encoding="utf-8"
        )
    )
    assert NotificationClaim.model_validate(data).model_dump() == data
    with pytest.raises(ValidationError):
        NotificationClaim.model_validate(data | {"sender_id": 20})
