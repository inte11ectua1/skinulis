"""All response datetime annotations share the UTC wire contract."""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.schemas.auth import UserProfile
from app.schemas.groups import (
    GroupProfile,
    InviteIssued,
    InviteProfile,
    LinkIssued,
    MemberProfile,
)
from app.schemas.timestamps import UTCDateTime


@pytest.mark.parametrize("offset", [0, 3, -7, 14])
@pytest.mark.parametrize("microsecond", [0, 123456])
def test_utc_timestamp_preserves_instant_precision_and_day_rollover(
    offset: int, microsecond: int
) -> None:
    original = datetime(
        2026, 10, 28, 1, 2, 3, microsecond, tzinfo=timezone(timedelta(hours=offset))
    )
    adapter = TypeAdapter[datetime](UTCDateTime)
    value = adapter.validate_python(original)
    assert value == original and value.tzinfo is UTC
    wire = json.loads(adapter.dump_json(value))
    assert wire.endswith("Z") and "+00:00" not in wire
    assert datetime.fromisoformat(wire) == original
    assert datetime.fromisoformat(wire).microsecond == microsecond
    assert original.utcoffset() == timedelta(hours=offset)
    assert adapter.validate_json(json.dumps(original.isoformat())) == value


@pytest.mark.parametrize("value", [datetime(2026, 10, 28), "2026-10-28T12:00:00"])
def test_naive_timestamps_are_rejected_without_assuming_a_timezone(
    value: object,
) -> None:
    with pytest.raises(ValidationError, match="timezone"):
        TypeAdapter[datetime](UTCDateTime).validate_python(value)


@pytest.mark.parametrize(
    "model,payload",
    [
        (UserProfile, {"id": 1, "email": None, "telegram_id": 123}),
        (GroupProfile, {"id": 1, "owner_id": 1, "name": "UTC"}),
        (MemberProfile, {"user_id": 1, "is_owner": True}),
        (InviteProfile, {"id": 1, "group_id": 1, "client_request_id": uuid4()}),
        (
            InviteIssued,
            {"id": 1, "group_id": 1, "client_request_id": uuid4(), "token": None},
        ),
        (LinkIssued, {"code": "<not-a-real-link-code>"}),
    ],
)
def test_every_response_datetime_field_uses_utc(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    original = datetime(
        2026, 10, 28, 12, 0, 0, 123456, tzinfo=timezone(timedelta(hours=3))
    )
    fields = {
        "created_at",
        "joined_at",
        "expires_at",
        "consumed_at",
        "revoked_at",
    } & model.model_fields.keys()
    data = {**payload, **dict.fromkeys(fields, original)}
    result = model.model_validate(data)
    for name in fields:
        assert getattr(result, name).tzinfo is UTC
        assert result.model_dump(mode="json")[name] == "2026-10-28T09:00:00.123456Z"
        with pytest.raises(ValidationError):
            model.model_validate({**data, name: datetime(2026, 10, 28)})
    if model in (InviteProfile, InviteIssued):
        optional = model.model_validate(
            {**data, "consumed_at": None, "revoked_at": None}
        )
        assert optional.model_dump(mode="json")["consumed_at"] is None
        assert optional.model_dump(mode="json")["revoked_at"] is None
