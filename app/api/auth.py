from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_settings
from app.config import Settings
from app.core.security import create_access_token
from app.db import get_session
from app.models import User
from app.schemas.auth import LoginInput, RegisterInput, TokenResponse, UserProfile
from app.schemas.system import ErrorResponse
from app.services.auth import authenticate_user, register_user

router = APIRouter(
    tags=["identity"],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        "4XX": {"model": ErrorResponse},
    },
)


@router.post(
    "/auth/register",
    status_code=201,
    response_model=UserProfile,
    responses={409: {"model": ErrorResponse}},
    summary="Register an email/password account (proposed T-05 contract)",
)
def register(
    payload: RegisterInput, session: Annotated[Session, Depends(get_session)]
) -> UserProfile:
    user = register_user(session, payload.email, payload.password.get_secret_value())
    return UserProfile.model_validate(user)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Obtain a short-lived Bearer access token",
)
def login(
    payload: LoginInput,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = authenticate_user(
        session, payload.email, payload.password.get_secret_value()
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(
        access_token=create_access_token(
            user.id,
            settings.require_jwt_secret(),
            settings.jwt_access_token_ttl_minutes,
        ),
        expires_in=settings.jwt_access_token_ttl_minutes * 60,
    )


@router.get(
    "/users/me", response_model=UserProfile, summary="Read the verified actor's profile"
)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserProfile:
    return UserProfile.model_validate(user)
