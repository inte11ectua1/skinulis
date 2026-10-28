"""T-03 health and approved T-06 service channel. No automatic write retries."""

import asyncio
from enum import StrEnum
from types import TracebackType
from typing import Literal, Protocol, Self
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from bot.dto import (
    GroupDraft,
    GroupProfile,
    InviteIssued,
    InviteProfile,
    MemberProfile,
    Page,
    UserProfile,
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

    async def _request[T: BaseModel](
        self,
        method: str,
        path: str,
        response_type: type[T],
        *,
        actor: int | None = None,
        body: dict[str, object] | None = None,
        offset: int | None = None,
        expected_status: int = 200,
    ) -> T:
        if self.is_closed:
            raise ApiError(ApiFailure.NETWORK)
        headers: dict[str, str] = {}
        if actor is not None:
            if not self._service_token:
                raise ApiError(ApiFailure.AUTH)
            if type(actor) is not int or not 0 < actor <= 2**63 - 1:
                raise ApiError(ApiFailure.INPUT)
            headers = {
                "X-Bot-Service-Token": self._service_token.get_secret_value(),
                "X-Telegram-ID": str(actor),
            }
        params = {"limit": 20, "offset": offset} if offset is not None else None
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT):
                response = await self._http.request(
                    method, path, headers=headers, json=body, params=params
                )
        except (httpx.TimeoutException, TimeoutError):
            raise ApiError(ApiFailure.TIMEOUT) from None
        except httpx.RequestError:
            raise ApiError(ApiFailure.NETWORK) from None

        if response.status_code != expected_status:
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
            return response_type.model_validate_json(response.content)
        except ValueError:
            raise ApiError(
                ApiFailure.UNEXPECTED, status_code=response.status_code
            ) from None

    async def profile(self, actor: int) -> UserProfile:
        return await self._request(
            "GET", "/internal/users/me", UserProfile, actor=actor
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
