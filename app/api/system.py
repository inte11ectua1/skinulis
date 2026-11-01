import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings
from app.core.errors import error_response
from app.db import get_session
from app.schemas.system import (
    ErrorResponse,
    HealthResponse,
    RootResponse,
    VersionResponse,
)
from skinulis_logging import Event, emit

router = APIRouter(tags=["system"])


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
        emit(Event.DATABASE_UNAVAILABLE, level=logging.WARNING)
        return error_response(503, "database_unavailable", "Database is unavailable")
    return HealthResponse()


@router.get("/version", response_model=VersionResponse)
def version(request: Request) -> VersionResponse:
    settings: Settings = request.app.state.settings
    return VersionResponse(version=__version__, commit_sha=settings.app_commit_sha)
