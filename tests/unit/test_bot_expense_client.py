"""Client wire matches the merged OpenAPI; no backend model imported in bot."""

import json
import secrets
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, TypeAdapter

from app.config import Settings
from app.main import create_app
from app.schemas import expenses as server
from bot.api_client import ApiClient, ApiError, ApiFailure
from bot.expense_dto import DRAFT, ExpenseMutation
from tests.unit.test_bot_expenses import O04, O05


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("fixture", [O04, O05])
@pytest.mark.parametrize("create_status", [200, 201])
async def test_exact_all_six_routes_headers_bodies_and_close(
    fixture: dict[str, Any], create_status: int
) -> None:
    key = uuid4()
    secret = secrets.token_urlsafe(48)
    business = fixture["preview_request"]
    mutation = fixture["create_response"]
    expected = [
        (
            "POST",
            "/internal/groups/100/expenses/preview",
            business,
            {},
            200,
            fixture["preview_response"],
        ),
        (
            "POST",
            "/internal/groups/100/expenses",
            business | {"client_request_id": str(key)},
            {},
            create_status,
            mutation,
        ),
        (
            "GET",
            "/internal/groups/100/expenses",
            None,
            {"limit": "20", "offset": "20"},
            200,
            {"items": [mutation["expense"]], "limit": 20, "offset": 20},
        ),
        ("GET", "/internal/expenses/7", None, {}, 200, mutation["expense"]),
        (
            "PUT",
            "/internal/expenses/7",
            business | {"expected_version": 5},
            {},
            200,
            mutation,
        ),
        (
            "DELETE",
            "/internal/expenses/7",
            None,
            {"expected_version": "5"},
            200,
            mutation,
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
        assert request.headers["X-Bot-Service-Token"] == secret
        assert request.headers["X-Telegram-ID"] == "123"
        assert "authorization" not in request.headers
        return httpx.Response(status, json=result)

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        draft = DRAFT.validate_python(business)
        assert (await api.preview_expense(123, 100, draft)).amount == fixture[
            "preview_response"
        ]["amount"]
        await api.create_expense(123, 100, draft, key)
        await api.expenses(123, 100, offset=20)
        await api.expense(123, 7)
        await api.update_expense(123, 7, draft, 5)
        await api.delete_expense(123, 7, 5)
    assert count == 6 and api.is_closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,kind",
    [
        (400, ApiFailure.INPUT),
        (401, ApiFailure.AUTH),
        (403, ApiFailure.FORBIDDEN),
        (404, ApiFailure.MISSING),
        (409, ApiFailure.CONFLICT),
        (500, ApiFailure.SERVER),
        (503, ApiFailure.SERVER),
        (429, ApiFailure.UNEXPECTED),
        (302, ApiFailure.UNEXPECTED),
        (202, ApiFailure.UNEXPECTED),
    ],
)
async def test_errors_are_safe_and_no_automatic_retry(
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
                "error": {"code": "private", "message": secret, "request_id": secret}
            },
        )

    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    ) as api:
        with pytest.raises(ApiError) as error:
            await api.create_expense(
                123, 100, DRAFT.validate_python(O05["preview_request"]), uuid4()
            )
        assert error.value.kind == kind and secret not in str(error.value)
    assert calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_errors_discard_exception_text(
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
            await api.expense(123, 7)
        assert secret not in str(error.value) and secret not in repr(error.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "value",
    [
        {},
        {"expense": {}},
        {"expense": O05["detail_response"]},
        {"expense": {**O05["detail_response"], "items": None}, "balances": None},
    ],
)
async def test_malformed_success_never_announces_success(value: dict[str, Any]) -> None:
    async with ApiClient(
        "http://api.test",
        service_token=SecretStr(secrets.token_urlsafe(48)),
        transport=httpx.MockTransport(lambda _: httpx.Response(201, json=value)),
    ) as api:
        with pytest.raises(ApiError) as error:
            await api.create_expense(
                123, 100, DRAFT.validate_python(O05["preview_request"]), uuid4()
            )
        assert error.value.kind == ApiFailure.UNEXPECTED


def test_requests_responses_and_openapi_match_actual_backend() -> None:
    settings = Settings(
        _env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(32))
    )
    schemas = create_app(settings).openapi()
    for fixture in [O04, O05]:
        TypeAdapter(server.PreviewInput).validate_python(fixture["preview_request"])
        TypeAdapter(server.PreviewResponse).validate_python(fixture["preview_response"])
        parsed = ExpenseMutation.model_validate_json(
            json.dumps(fixture["create_response"])
        )
        server.ExpenseMutation.model_validate_json(parsed.model_dump_json())
    union = schemas["paths"]["/internal/groups/{group_id}/expenses/preview"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    assert set(union["discriminator"]["mapping"]) == {"equal", "custom", "by_items"}
    backend = schemas["components"]["schemas"]
    assert set(backend["ReceiptPreviewProfile"]["properties"]) == {
        "group_id",
        "payer_id",
        "title",
        "split_mode",
        "amount",
        "shares",
        "items",
    }
    assert "items" not in backend["ExpenseProfile"]["properties"]
    assert set(backend["ByItemsInput"]["properties"]) == {
        "title",
        "split_mode",
        "items",
    }
    delete_query = schemas["paths"]["/internal/expenses/{expense_id}"]["delete"][
        "parameters"
    ]
    assert any(
        p["name"] == "expected_version" and p["in"] == "query" and p["required"]
        for p in delete_query
    )
