"""Safe HTTP errors: no validation input, exception arguments or traceback in logs."""

import logging
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.schemas.system import ErrorDetail, ErrorResponse
from skinulis_logging import Event, Fields, current_request_id, emit, request_context


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
    request_id = current_request_id()
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
        with request_context() as request_id:
            started = perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                # Catch before ServerErrorMiddleware can re-raise raw exception args.
                response = error_response(
                    500, "internal_error", "Internal server error"
                )
                emit(Event.HTTP_FAILED, level=logging.ERROR)
            response.headers["X-Request-ID"] = request_id
            route = getattr(request.scope.get("route"), "path", None)
            status = response.status_code
            emit(
                Event.HTTP_COMPLETED,
                level=logging.ERROR
                if status >= 500
                else logging.WARNING
                if status >= 400
                else logging.INFO,
                fields=Fields(
                    status=status,
                    method=request.method,
                    route=route,
                    duration_ms=int((perf_counter() - started) * 1000),
                ),
            )
            return response
