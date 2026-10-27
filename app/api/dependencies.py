"""Reusable verified JWT actor for T-06; never accepts actor IDs from JSON."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ApiError
from app.core.security import InvalidAccessToken, decode_access_token
from app.db import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    failure = ApiError(401, "invalid_token", "Invalid or missing access token")
    if credentials is None:
        raise failure
    try:
        user_id = decode_access_token(
            credentials.credentials, settings.require_jwt_secret()
        )
    except InvalidAccessToken:
        raise failure from None
    user = session.get(User, user_id)
    if user is None:
        raise failure
    return user
