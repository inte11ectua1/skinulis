import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings
from app.db import get_session
from app.schemas.system import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    RootResponse,
    VersionResponse,
)

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=RootResponse)
def root() -> RootResponse:
    return RootResponse()


@router.get(
    "/health", response_model=HealthResponse, responses={503: {"model": ErrorResponse}}
)
def health(
    session: Annotated[Session, Depends(get_session)],
) -> HealthResponse | JSONResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # DB exceptions can contain connection details; do not log them or their args.
        request_id = str(uuid4())
        logger.warning("Database health check failed; request_id=%s", request_id)
        error = ErrorResponse(
            error=ErrorDetail(
                code="database_unavailable",
                message="Database is unavailable",
                request_id=request_id,
            )
        )
        return JSONResponse(
            status_code=503,
            content=error.model_dump(),
            headers={"X-Request-ID": request_id},
        )
    return HealthResponse()


@router.get("/version", response_model=VersionResponse)
def version(request: Request) -> VersionResponse:
    settings: Settings = request.app.state.settings
    return VersionResponse(version=__version__, commit_sha=settings.app_commit_sha)
