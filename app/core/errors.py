"""Safe HTTP errors: no validation input, exception arguments or traceback in logs."""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.schemas.system import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, *, auth_scheme: str = "Bearer"
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.auth_scheme = auth_scheme


def error_response(
    status: int, code: str, message: str, *, auth_scheme: str = "Bearer"
) -> JSONResponse:
    request_id = str(uuid4())
    # Exception handlers build a new response, bypassing router response headers.
    headers = {"X-Request-ID": request_id, "Cache-Control": "no-store"}
    if status == 401:
        headers["WWW-Authenticate"] = auth_scheme
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message, request_id=request_id)
        ).model_dump(),
        headers=headers,
    )


def install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return error_response(
            error.status, error.code, error.message, auth_scheme=error.auth_scheme
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return error_response(400, "validation_error", "Invalid request data")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, "http_error", "Request failed")

    @application.middleware("http")
    async def safe_server_errors(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception:
            response = error_response(500, "internal_error", "Internal server error")
            logger.error(
                "Request failed; request_id=%s", response.headers["X-Request-ID"]
            )
            # Catch before ServerErrorMiddleware can re-raise and log secret-bearing args.
            return response
