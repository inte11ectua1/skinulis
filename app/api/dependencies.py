"""Reusable verified JWT actor for T-06; never accepts actor IDs from JSON."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.core.errors import ApiError
from app.core.security import InvalidAccessToken, decode_access_token
from app.db import Database, get_database
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if "X-Bot-Service-Token" in request.headers or "X-Telegram-ID" in request.headers:
        raise ApiError(400, "ambiguous_actor", "Use one authentication channel")
    failure = ApiError(401, "invalid_token", "Invalid or missing access token")
    if credentials is None:
        raise failure
    try:
        user_id = decode_access_token(
            credentials.credentials, settings.require_jwt_secret()
        )
    except InvalidAccessToken:
        raise failure from None
    # Authentication owns only this read transaction, never the endpoint's work.
    # Detach the fully loaded scalar User before close/rollback can expire it.
    with database.sessions() as session:
        user = session.get(User, user_id)
        if user is None:
            raise failure
        session.expunge(user)
    return user
