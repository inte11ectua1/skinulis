"""Explicit onboarding and single-use linking; never merge existing users."""

from datetime import timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.identity_tokens import new_secret, secret_digest, utc_now
from app.models import TelegramLinkCode, User
from app.services.transactions import write_transaction


def lock_telegram_identity(session: Session, telegram_id: int) -> None:
    # Reserved advisory namespace: negative signed BIGINT Telegram IDs. No hash collision.
    # Identity operations never acquire group locks or run inside group write services.
    session.execute(
        text("SELECT pg_advisory_xact_lock(CAST(:key AS BIGINT))"),
        {"key": -telegram_id},
    )


def bootstrap_user(session: Session, telegram_id: int) -> User:
    with write_transaction(session):
        lock_telegram_identity(session, telegram_id)
        user = session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            user = User(telegram_id=telegram_id)
            session.add(user)
            session.flush()
    return user


def issue_link_code(session: Session, user_id: int) -> tuple[str, TelegramLinkCode]:
    with write_transaction(session):
        user = session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise ApiError(401, "invalid_token", "Invalid or missing access token")
        if user.email is None:
            raise ApiError(
                409, "email_profile_required", "An email account is required"
            )
        if user.telegram_id is not None:
            raise ApiError(
                409,
                "telegram_already_linked",
                "Account already has a Telegram identity",
            )
        now = utc_now()
        session.execute(
            update(TelegramLinkCode)
            .where(
                TelegramLinkCode.user_id == user_id,
                TelegramLinkCode.consumed_at.is_(None),
                TelegramLinkCode.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        raw = new_secret()
        code = TelegramLinkCode(
            user_id=user_id,
            token_hash=secret_digest(raw),
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        session.add(code)
        session.flush()
    return raw, code


def link_telegram(session: Session, telegram_id: int, raw: str) -> User:
    failure = ApiError(404, "link_code_invalid", "Link code is invalid or unavailable")
    with write_transaction(session):
        lock_telegram_identity(session, telegram_id)
        user_id = session.scalar(
            select(TelegramLinkCode.user_id).where(
                TelegramLinkCode.token_hash == secret_digest(raw)
            )
        )
        if user_id is None:
            raise failure
        # User precedes code for both issuance and consumption. Never code -> user.
        user = session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        code = session.scalar(
            select(TelegramLinkCode)
            .where(TelegramLinkCode.token_hash == secret_digest(raw))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utc_now()
        if (
            user is None
            or code is None
            or code.consumed_at is not None
            or code.revoked_at is not None
            or now >= code.expires_at
        ):
            raise failure
        if (
            session.scalar(select(User.id).where(User.telegram_id == telegram_id))
            is not None
        ):
            raise ApiError(
                409, "telegram_identity_conflict", "Cannot merge existing accounts"
            )
        if user.telegram_id is not None:
            raise ApiError(
                409,
                "telegram_already_linked",
                "Account already has a Telegram identity",
            )
        if user.email is None:
            raise ApiError(
                409, "email_profile_required", "An email account is required"
            )
        user.telegram_id = telegram_id
        code.consumed_at = now
        session.flush()
    return user
