"""Proposed onboarding operations; bot handlers and Telegram updates stay in L-03."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.groups import ERRORS, no_store
from app.api.telegram_dependencies import get_bot_user, get_telegram_actor
from app.db import get_session
from app.models import User
from app.schemas.auth import UserProfile
from app.schemas.groups import EmptyInput, LinkInput, LinkIssued
from app.services.telegram_identity import (
    bootstrap_user,
    issue_link_code,
    link_telegram,
)

router = APIRouter(
    tags=["Telegram identity (proposed T-06)"],
    responses=ERRORS,
    dependencies=[Depends(no_store)],
)


@router.get("/internal/users/me", response_model=UserProfile)
def me(user: Annotated[User, Depends(get_bot_user)]) -> UserProfile:
    """Read only; a new Telegram actor receives 404 without creating a profile."""
    return UserProfile.model_validate(user)


@router.post("/internal/users/bootstrap", response_model=UserProfile)
def bootstrap(
    payload: EmptyInput,
    telegram_id: Annotated[int, Depends(get_telegram_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> UserProfile:
    """Call only after explicit Create consent; repeats return the same profile."""
    return UserProfile.model_validate(bootstrap_user(session, telegram_id))


@router.post("/users/me/telegram-link-code", status_code=201, response_model=LinkIssued)
def issue(
    payload: EmptyInput,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> LinkIssued:
    """JWT email account only. A new issuance invalidates previous unused codes."""
    raw, code = issue_link_code(session, user.id)
    return LinkIssued(code=raw, expires_at=code.expires_at)


@router.post("/internal/users/telegram-link", response_model=UserProfile)
def link(
    payload: LinkInput,
    telegram_id: Annotated[int, Depends(get_telegram_actor)],
    session: Annotated[Session, Depends(get_session)],
) -> UserProfile:
    """Single use, 10 minutes, no merge. After timeout read internal/users/me first."""
    return UserProfile.model_validate(
        link_telegram(session, telegram_id, payload.code.get_secret_value())
    )
