"""Sync auth services; registration owns one atomic DB transaction."""

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import dummy_password_hash, hash_password, verify_password
from app.models import User


def register_user(session: Session, email: str, password: str) -> User:
    encoded = hash_password(password)
    try:
        with session.begin():
            user = User(email=email, password_hash=encoded)
            session.add(user)
            session.flush()
    except IntegrityError as error:
        if (
            isinstance(error.orig, UniqueViolation)
            and error.orig.diag.constraint_name == "uq_users_email"
        ):
            raise ApiError(
                409, "email_already_registered", "Email already registered"
            ) from None
        raise
    return user


def authenticate_user(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    encoded = user.password_hash if user is not None else None
    valid = verify_password(password, encoded if encoded else dummy_password_hash())
    if not valid or user is None or encoded is None:
        raise ApiError(401, "invalid_credentials", "Invalid credentials")
    return user
