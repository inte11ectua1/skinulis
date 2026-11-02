"""T-03 health and approved T-06 service channel. No automatic write retries."""

import asyncio
import logging
from enum import StrEnum
from types import TracebackType
from typing import Literal, Protocol, Self
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, TypeAdapter

from bot.dto import (
    GroupDraft,
    GroupProfile,
    InviteIssued,
    InviteProfile,
    MemberProfile,
    Page,
    UserProfile,
)
from bot.expense_dto import (
    EXPENSE,
    PREVIEW,
    ExpenseDraft,
    ExpenseMutation,
    ExpensePreview,
    ExpenseProfile,
)
from bot.settlement_dto import (
    Balances,
    Direction,
    NotificationClaim,
    Plan,
    SettlementCreate,
    SettlementMutation,
    SettlementProfile,
    SettlementStatus,
)
from skinulis_logging import (
    Event,
    Fields,
    Outcome,
    canonical_request_id,
    current_request_id,
    emit,
)

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


class BotApi(HealthApi, Protocol):
    async def claim_settlement_notification(
        self, actor: int, settlement_id: int
    ) -> NotificationClaim | None: ...

    async def balances(self, actor: int, group_id: int) -> Balances: ...
    async def settlement_plan(self, actor: int, group_id: int) -> Plan: ...
    async def create_settlement(
        self, actor: int, group_id: int, draft: SettlementCreate
    ) -> SettlementMutation: ...
    async def settlements(
        self,
        actor: int,
        group_id: int,
        *,
        offset: int = 0,
        status: SettlementStatus | None = None,
        direction: Direction = "all",
    ) -> Page[SettlementProfile]: ...
    async def confirm_settlement(
        self, actor: int, settlement_id: int
    ) -> SettlementMutation: ...
    async def reject_settlement(
        self, actor: int, settlement_id: int
    ) -> SettlementMutation: ...
    async def cancel_settlement(
        self, actor: int, settlement_id: int
    ) -> SettlementMutation: ...
    async def preview_expense(
        self, actor: int, group_id: int, draft: ExpenseDraft
    ) -> ExpensePreview: ...
    async def create_expense(
        self, actor: int, group_id: int, draft: ExpenseDraft, key: UUID
    ) -> ExpenseMutation: ...
    async def expenses(
        self, actor: int, group_id: int, *, offset: int = 0
    ) -> Page[ExpenseProfile]: ...
    async def expense(self, actor: int, expense_id: int) -> ExpenseProfile: ...
    async def update_expense(
        self, actor: int, expense_id: int, draft: ExpenseDraft, version: int
    ) -> ExpenseMutation: ...
    async def delete_expense(
        self, actor: int, expense_id: int, version: int
    ) -> ExpenseMutation: ...
    async def profile(self, actor: int) -> UserProfile: ...
    async def bootstrap(self, actor: int) -> UserProfile: ...
    async def link(self, actor: int, code: SecretStr) -> UserProfile: ...
    async def groups(self, actor: int, *, offset: int = 0) -> Page[GroupProfile]: ...
    async def create_group(self, actor: int, draft: GroupDraft) -> GroupProfile: ...
    async def group(self, actor: int, group_id: int) -> GroupProfile: ...
    async def members(
        self, actor: int, group_id: int, *, offset: int = 0
    ) -> Page[MemberProfile]: ...
    async def invites(
        self, actor: int, group_id: int, *, offset: int = 0
    ) -> Page[InviteProfile]: ...
    async def issue_invite(
        self, actor: int, group_id: int, key: UUID
    ) -> InviteIssued: ...
    async def revoke_invite(
        self, actor: int, group_id: int, invite_id: int
    ) -> InviteProfile: ...
    async def join(self, actor: int, token: SecretStr) -> GroupProfile: ...


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        service_token: SecretStr | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._service_token = service_token
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
        return await self._request("GET", "/health", HealthResult)

    async def _request[T](
        self,
        method: str,
        path: str,
        response_type: type[T] | TypeAdapter[T],
        *,
        actor: int | None = None,
        body: dict[str, object] | None = None,
        offset: int | None = None,
        expected_status: int | tuple[int, ...] = 200,
        version: int | None = None,
        query: dict[str, str | int] | None = None,
    ) -> T:
        correlation = current_request_id()

        def diagnostic(kind: ApiFailure, status: int | None = None) -> None:
            emit(
                Event.CLIENT_FAILED,
                level=logging.WARNING,
                fields=Fields(
                    method=method,
                    status=status,
                    outcome=Outcome(kind.value),
                    request_id=correlation,
                ),
            )

        if self.is_closed:
            diagnostic(ApiFailure.NETWORK)
            raise ApiError(ApiFailure.NETWORK)
        headers: dict[str, str] = {}
        if actor is not None:
            if not self._service_token:
                diagnostic(ApiFailure.AUTH)
                raise ApiError(ApiFailure.AUTH)
            if type(actor) is not int or not 0 < actor <= 2**63 - 1:
                diagnostic(ApiFailure.INPUT)
                raise ApiError(ApiFailure.INPUT)
            headers = {
                "X-Bot-Service-Token": self._service_token.get_secret_value(),
                "X-Telegram-ID": str(actor),
            }
        params: dict[str, str | int] | None = (
            {"limit": 20, "offset": offset} if offset is not None else None
        )
        if version is not None:
            params = {"expected_version": version}
        if query:
            params = (params or {}) | query
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT):
                response = await self._http.request(
                    method, path, headers=headers, json=body, params=params
                )
        except (httpx.TimeoutException, TimeoutError):
            diagnostic(ApiFailure.TIMEOUT)
            raise ApiError(ApiFailure.TIMEOUT) from None
        except httpx.RequestError:
            diagnostic(ApiFailure.NETWORK)
            raise ApiError(ApiFailure.NETWORK) from None

        correlation = (
            canonical_request_id(response.headers.get("X-Request-ID")) or correlation
        )
        statuses = (
            (expected_status,) if isinstance(expected_status, int) else expected_status
        )
        if response.status_code not in statuses:
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
            diagnostic(kind, response.status_code)
            raise ApiError(kind, status_code=response.status_code, detail=detail)
        try:
            adapter = (
                response_type
                if isinstance(response_type, TypeAdapter)
                else TypeAdapter(response_type)
            )
            if response.status_code == 204:
                if response.content:
                    raise ValueError("Expected empty response")
                result = adapter.validate_python(None)
            else:
                result = adapter.validate_json(response.content)
                if result is None:
                    raise ValueError("Unexpected null response")
            emit(
                Event.CLIENT_COMPLETED,
                fields=Fields(
                    method=method,
                    status=response.status_code,
                    outcome=Outcome.OK,
                    request_id=correlation,
                ),
            )
            return result
        except ValueError:
            diagnostic(ApiFailure.UNEXPECTED, response.status_code)
            raise ApiError(
                ApiFailure.UNEXPECTED, status_code=response.status_code
            ) from None

    async def profile(self, actor: int) -> UserProfile:
        return await self._request(
            "GET", "/internal/users/me", UserProfile, actor=actor
        )

    async def balances(self, actor: int, group_id: int) -> Balances:
        return await self._request(
            "GET", f"/internal/groups/{group_id}/balances", Balances, actor=actor
        )

    async def claim_settlement_notification(
        self, actor: int, settlement_id: int
    ) -> NotificationClaim | None:
        return await self._request(
            "POST",
            f"/internal/settlements/{settlement_id}/notification-claim",
            TypeAdapter(NotificationClaim | None),
            actor=actor,
            expected_status=(200, 204),
        )

    async def settlement_plan(self, actor: int, group_id: int) -> Plan:
        return await self._request(
            "GET", f"/internal/groups/{group_id}/settlement-plan", Plan, actor=actor
        )

    async def create_settlement(
        self, actor: int, group_id: int, draft: SettlementCreate
    ) -> SettlementMutation:
        return await self._request(
            "POST",
            f"/internal/groups/{group_id}/settlements",
            SettlementMutation,
            actor=actor,
            body=draft.model_dump(mode="json"),
            expected_status=(200, 201),
        )

    async def settlements(
        self,
        actor: int,
        group_id: int,
        *,
        offset: int = 0,
        status: SettlementStatus | None = None,
        direction: Direction = "all",
    ) -> Page[SettlementProfile]:
        query: dict[str, str | int] = {"direction": direction}
        if status is not None:
            query["status"] = status
        return await self._request(
            "GET",
            f"/internal/groups/{group_id}/settlements",
            Page[SettlementProfile],
            actor=actor,
            offset=offset,
            query=query,
        )

    async def confirm_settlement(
        self, actor: int, settlement_id: int
    ) -> SettlementMutation:
        return await self._request(
            "POST",
            f"/internal/settlements/{settlement_id}/confirm",
            SettlementMutation,
            actor=actor,
            body={},
        )

    async def reject_settlement(
        self, actor: int, settlement_id: int
    ) -> SettlementMutation:
        return await self._request(
            "POST",
            f"/internal/settlements/{settlement_id}/reject",
            SettlementMutation,
            actor=actor,
            body={},
        )

    async def cancel_settlement(
        self, actor: int, settlement_id: int
    ) -> SettlementMutation:
        return await self._request(
            "POST",
            f"/internal/settlements/{settlement_id}/cancel",
            SettlementMutation,
            actor=actor,
            body={},
        )

    async def preview_expense(
        self, actor: int, group_id: int, draft: ExpenseDraft
    ) -> ExpensePreview:
        return await self._request(
            "POST",
            f"/internal/groups/{group_id}/expenses/preview",
            PREVIEW,
            actor=actor,
            body=draft.model_dump(mode="json"),
        )

    async def create_expense(
        self, actor: int, group_id: int, draft: ExpenseDraft, key: UUID
    ) -> ExpenseMutation:
        return await self._request(
            "POST",
            f"/internal/groups/{group_id}/expenses",
            ExpenseMutation,
            actor=actor,
            body=draft.model_dump(mode="json") | {"client_request_id": str(key)},
            expected_status=(200, 201),
        )

    async def expenses(
        self, actor: int, group_id: int, *, offset: int = 0
    ) -> Page[ExpenseProfile]:
        return await self._request(
            "GET",
            f"/internal/groups/{group_id}/expenses",
            Page[ExpenseProfile],
            actor=actor,
            offset=offset,
        )

    async def expense(self, actor: int, expense_id: int) -> ExpenseProfile:
        return await self._request(
            "GET", f"/internal/expenses/{expense_id}", EXPENSE, actor=actor
        )

    async def update_expense(
        self, actor: int, expense_id: int, draft: ExpenseDraft, version: int
    ) -> ExpenseMutation:
        return await self._request(
            "PUT",
            f"/internal/expenses/{expense_id}",
            ExpenseMutation,
            actor=actor,
            body=draft.model_dump(mode="json") | {"expected_version": version},
        )

    async def delete_expense(
        self, actor: int, expense_id: int, version: int
    ) -> ExpenseMutation:
        return await self._request(
            "DELETE",
            f"/internal/expenses/{expense_id}",
            ExpenseMutation,
            actor=actor,
            version=version,
        )

    async def bootstrap(self, actor: int) -> UserProfile:
        return await self._request(
            "POST", "/internal/users/bootstrap", UserProfile, actor=actor, body={}
        )

    async def link(self, actor: int, code: SecretStr) -> UserProfile:
        return await self._request(
            "POST",
            "/internal/users/telegram-link",
            UserProfile,
            actor=actor,
            body={"code": code.get_secret_value()},
        )

    async def groups(self, actor: int, *, offset: int = 0) -> Page[GroupProfile]:
        return await self._request(
            "GET", "/internal/groups", Page[GroupProfile], actor=actor, offset=offset
        )

    async def create_group(self, actor: int, draft: GroupDraft) -> GroupProfile:
        return await self._request(
            "POST",
            "/internal/groups",
            GroupProfile,
            actor=actor,
            body=draft.model_dump(mode="json"),
            expected_status=201,
        )

    async def group(self, actor: int, group_id: int) -> GroupProfile:
        return await self._request(
            "GET", f"/internal/groups/{group_id}", GroupProfile, actor=actor
        )

    async def members(
        self, actor: int, group_id: int, *, offset: int = 0
    ) -> Page[MemberProfile]:
        return await self._request(
            "GET",
            f"/internal/groups/{group_id}/members",
            Page[MemberProfile],
            actor=actor,
            offset=offset,
        )

    async def invites(
        self, actor: int, group_id: int, *, offset: int = 0
    ) -> Page[InviteProfile]:
        return await self._request(
            "GET",
            f"/internal/groups/{group_id}/invites",
            Page[InviteProfile],
            actor=actor,
            offset=offset,
        )

    async def issue_invite(self, actor: int, group_id: int, key: UUID) -> InviteIssued:
        return await self._request(
            "POST",
            f"/internal/groups/{group_id}/invites",
            InviteIssued,
            actor=actor,
            body={"client_request_id": str(key)},
            expected_status=201,
        )

    async def revoke_invite(
        self, actor: int, group_id: int, invite_id: int
    ) -> InviteProfile:
        return await self._request(
            "DELETE",
            f"/internal/groups/{group_id}/invites/{invite_id}",
            InviteProfile,
            actor=actor,
        )

    async def join(self, actor: int, token: SecretStr) -> GroupProfile:
        return await self._request(
            "POST",
            "/internal/group-invites/join",
            GroupProfile,
            actor=actor,
            body={"token": token.get_secret_value()},
        )
