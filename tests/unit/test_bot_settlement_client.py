"""Approved M4 wire, filters, errors, and independent DTO/OpenAPI compatibility."""

import json
import secrets
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import Settings
from app.main import create_app
from app.schemas.balances import BalancesResponse, PlanResponse
from app.schemas.settlements import SettlementCreate as BackendCreate
from app.schemas.settlements import SettlementMutation as BackendMutation
from bot.api_client import ApiClient, ApiError, ApiFailure
from bot.settlement_dto import Balances, Plan, SettlementCreate, SettlementMutation
from tests.unit.test_bot_settlements import O06, O07


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("post_status", [200, 201])
async def test_seven_operations_exact_wire_actor_filters_and_close(
    post_status: int,
) -> None:
    secret = secrets.token_urlsafe(48)
    draft = SettlementCreate(receiver_id=10, amount="500.00", client_request_id=uuid4())
    expected = [
        ("GET", "/internal/groups/10/balances", None, {}, 200, O06["balances"]),
        ("GET", "/internal/groups/10/settlement-plan", None, {}, 200, O06["plan"]),
        (
            "POST",
            "/internal/groups/10/settlements",
            draft.model_dump(mode="json"),
            {},
            post_status,
            O07["create"],
        ),
        (
            "GET",
            "/internal/groups/10/settlements",
            None,
            {
                "limit": "20",
                "offset": "20",
                "status": "pending",
                "direction": "incoming",
            },
            200,
            O07["page"],
        ),
        ("POST", "/internal/settlements/123/confirm", {}, {}, 200, O07["confirmed"]),
        ("POST", "/internal/settlements/123/reject", {}, {}, 200, O07["rejected"]),
        ("POST", "/internal/settlements/123/cancel", {}, {}, 200, O07["cancelled"]),
        (
            "GET",
            "/internal/groups/10/settlements",
            None,
            {"limit": "20", "offset": "0", "direction": "all"},
            200,
            O07["page"],
        ),
    ]
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        method, path, body, query, status, result = expected[count]
        count += 1
        assert (request.method, request.url.path) == (method, path)
        assert (json.loads(request.content) if request.content else None) == body
        assert dict(request.url.params) == query
        assert (
            request.headers["X-Telegram-ID"] == "123"
            and request.headers["X-Bot-Service-Token"] == secret
        )
        assert "authorization" not in request.headers
        assert (
            not body
            or not {"sender_id", "telegram_id", "author_id", "payer_id"} & body.keys()
        )
        return httpx.Response(status, json=result)

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        await api.balances(123, 10)
        await api.settlement_plan(123, 10)
        await api.create_settlement(123, 10, draft)
        await api.settlements(
            123, 10, offset=20, status="pending", direction="incoming"
        )
        await api.confirm_settlement(123, 123)
        await api.reject_settlement(123, 123)
        await api.cancel_settlement(123, 123)
        await api.settlements(123, 10)
    assert count == 8 and api.is_closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,kind",
    [
        (400, ApiFailure.INPUT),
        (401, ApiFailure.AUTH),
        (403, ApiFailure.FORBIDDEN),
        (404, ApiFailure.MISSING),
        (409, ApiFailure.CONFLICT),
        (429, ApiFailure.UNEXPECTED),
        (500, ApiFailure.SERVER),
        (503, ApiFailure.SERVER),
        (202, ApiFailure.UNEXPECTED),
        (302, ApiFailure.UNEXPECTED),
    ],
)
async def test_http_errors_no_retry_or_raw_diagnostic(
    status: int, kind: ApiFailure
) -> None:
    secret = secrets.token_urlsafe(48)
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            json={
                "error": {"code": "unknown", "message": secret, "request_id": secret}
            },
        )

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        with pytest.raises(ApiError) as error:
            await api.confirm_settlement(123, 123)
        assert error.value.kind == kind and secret not in str(error.value) + repr(
            error.value
        )
    assert calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_timeout_redacted_without_automatic_retry(
    exception: type[httpx.RequestError],
) -> None:
    secret = secrets.token_urlsafe(48)

    def respond(_: httpx.Request) -> httpx.Response:
        raise exception(secret)

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        with pytest.raises(ApiError) as error:
            await api.create_settlement(
                123,
                10,
                SettlementCreate(
                    receiver_id=10, amount="1.00", client_request_id=uuid4()
                ),
            )
        assert secret not in str(error.value) + repr(error.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "malformed",
    [
        {},
        {"settlement": {}},
        {"settlement": {**O07["create"]["settlement"], "status": "sent"}},
        {"settlement": {**O07["create"]["settlement"], "sender_id": True}},
        {"settlement": {**O07["create"]["settlement"], "amount": 500.0}},
    ],
)
async def test_malformed_success_cannot_become_confirmed(
    malformed: dict[str, Any],
) -> None:
    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=malformed)),
    ) as api:
        with pytest.raises(ApiError) as error:
            await api.confirm_settlement(123, 123)
        assert error.value.kind == ApiFailure.UNEXPECTED


@pytest.mark.parametrize(
    "bad",
    [
        "0.00",
        "-0.01",
        "+1.00",
        "1,00",
        "1e1",
        "01.00",
        "1.000",
        " 1.00",
        "١.٠٠",
        "9" * 21,
    ],
)
def test_input_shape_and_server_final_validation(bad: str) -> None:
    with pytest.raises(ValidationError):
        SettlementCreate(receiver_id=10, amount=bad, client_request_id=uuid4())


@pytest.mark.parametrize(
    "extra",
    ["sender_id", "telegram_id", "group_id", "status", "payer_id", "resolved_at"],
)
def test_client_cannot_send_actor_or_server_fields(extra: str) -> None:
    with pytest.raises(ValidationError):
        SettlementCreate.model_validate(
            {
                "receiver_id": 10,
                "amount": "1.00",
                "client_request_id": uuid4(),
                extra: 20,
            }
        )


def test_fixtures_models_and_generated_openapi() -> None:
    pairs: list[tuple[type[BaseModel], type[BaseModel], dict[str, Any]]] = [
        (Balances, BalancesResponse, O06["balances"]),
        (Plan, PlanResponse, O06["plan"]),
    ]
    for model, backend, value in pairs:
        parsed = model.model_validate_json(json.dumps(value))
        backend.model_validate_json(parsed.model_dump_json())
    for name in ["create", "confirmed", "rejected", "cancelled"]:
        parsed = SettlementMutation.model_validate_json(json.dumps(O07[name]))
        BackendMutation.model_validate_json(parsed.model_dump_json())
    # Beyond the expense ceiling, up to server BIGINT. No bot financial parser.
    for amount in ["1000001.00", "92233720368547758.07"]:
        draft = SettlementCreate(
            receiver_id=10, amount=amount, client_request_id=uuid4()
        )
        BackendCreate.model_validate_json(draft.model_dump_json())
    Balances.model_validate(
        {
            "group_id": 10,
            "balances": [
                {"user_id": 10, "balance": "276701161105643274.21"},
                {"user_id": 20, "balance": "-276701161105643274.21"},
            ],
        }
    )
    settings = Settings(
        _env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(32))
    )
    spec = create_app(settings).openapi()
    schema = spec["components"]["schemas"]["SettlementCreate"]
    assert set(schema["properties"]) == {"receiver_id", "amount", "client_request_id"}
    assert spec["paths"]["/internal/groups/{group_id}/settlements"]["post"][
        "responses"
    ].keys() >= {"200", "201"}
    params = spec["paths"]["/internal/groups/{group_id}/settlements"]["get"][
        "parameters"
    ]
    assert {p["name"] for p in params} >= {"limit", "offset", "status", "direction"}
    assert "/internal/settlements/{settlement_id}" not in spec["paths"]
