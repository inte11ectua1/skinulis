"""Typed client for the existing GET /health contract (T-03).

TODO(UQ-01/02): bot-service actor/auth, onboarding and invitations.
TODO(UQ-03..09): approved finance/preview, errors, pagination and replay contracts.
No speculative domain requests, service headers, automatic retries or DB imports.
"""

import asyncio
from enum import StrEnum
from types import TracebackType
from typing import Literal, Protocol, Self

import httpx
from pydantic import BaseModel, ConfigDict

TOTAL_TIMEOUT = 10.0


class HealthResult(BaseModel):
    """Fields already returned by app/schemas/system.py; no implicit success defaults."""

    model_config = ConfigDict(strict=True)
    status: Literal["ok"]
    database: Literal["ok"]


class ErrorDetail(BaseModel):
    model_config = ConfigDict(strict=True)
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class ApiFailure(StrEnum):
    INPUT = "input"
    AUTH = "auth"
    FORBIDDEN = "forbidden"
    MISSING = "missing"
    CONFLICT = "conflict"
    SERVER = "server"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UNEXPECTED = "unexpected"


MESSAGES: dict[ApiFailure, str] = {
    ApiFailure.INPUT: "Не удалось принять данные. Проверьте введённые значения.",
    ApiFailure.AUTH: (
        "Не удалось подтвердить доступ к сервису. Попробуйте позже. "
        "Пароль в Telegram не нужен."
    ),
    ApiFailure.FORBIDDEN: "Для этого действия недостаточно прав.",
    ApiFailure.MISSING: "Группа или запись недоступна.",
    ApiFailure.CONFLICT: "Состояние изменилось. Обновите данные перед повтором действия.",
    ApiFailure.SERVER: "Сервис временно не смог обработать запрос. Попробуйте позже.",
    ApiFailure.TIMEOUT: "Не удалось дождаться ответа сервиса. Попробуйте загрузить позже.",
    ApiFailure.NETWORK: "Не удалось связаться с сервисом. Попробуйте позже.",
    ApiFailure.UNEXPECTED: "Получен непонятный ответ сервиса. Попробуйте обновить позже.",
}


class ApiError(Exception):
    """Only a local safe message in str/repr; remote diagnostics never reach chat."""

    def __init__(
        self,
        kind: ApiFailure,
        *,
        status_code: int | None = None,
        detail: ErrorDetail | None = None,
    ) -> None:
        super().__init__(MESSAGES[kind])
        self.kind = kind
        self.status_code = status_code
        self.error_code = detail.code if detail else None
        self.request_id = detail.request_id if detail else None
        # Do not retain/echo/log the untrusted server message.


class HealthApi(Protocol):
    async def health(self) -> HealthResult: ...


class ApiClient:
    def __init__(
        self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(5.0, connect=3.0),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    @property
    def is_closed(self) -> bool:
        return self._http.is_closed

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def health(self) -> HealthResult:
        """GET /health without a body or auth; never creates a user or financial record."""
        if self.is_closed:
            raise ApiError(ApiFailure.NETWORK)
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT):
                response = await self._http.get("/health")
        except (httpx.TimeoutException, TimeoutError):
            raise ApiError(ApiFailure.TIMEOUT) from None
        except httpx.RequestError:
            raise ApiError(ApiFailure.NETWORK) from None

        if response.status_code != 200:
            kinds = {
                400: ApiFailure.INPUT,
                401: ApiFailure.AUTH,
                403: ApiFailure.FORBIDDEN,
                404: ApiFailure.MISSING,
                409: ApiFailure.CONFLICT,
            }
            kind = kinds.get(response.status_code, ApiFailure.UNEXPECTED)
            if 500 <= response.status_code <= 599:
                kind = ApiFailure.SERVER
            try:
                detail = ErrorEnvelope.model_validate(response.json()).error
            except ValueError:
                detail = None
            raise ApiError(kind, status_code=response.status_code, detail=detail)
        try:
            return HealthResult.model_validate(response.json())
        except ValueError:
            raise ApiError(ApiFailure.UNEXPECTED, status_code=200) from None
