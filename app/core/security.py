"""Password/JWT primitives. Algorithms and claims are never chosen by token input."""

import re
import secrets
from datetime import UTC, datetime
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.profiles import RFC_9106_LOW_MEMORY

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "skinulis"
JWT_AUDIENCE = "skinulis-api"
MAX_USER_ID = 2**63 - 1
REQUIRED_CLAIMS = ["sub", "iat", "nbf", "exp", "iss", "aud", "token_use"]
_hasher = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)


class InvalidAccessToken(Exception):
    """Safe boundary exception: never retain the original token or decode error."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    # Same expensive verification for an unknown email / Telegram-only credential.
    return hash_password(secrets.token_urlsafe(32))


def create_access_token(user_id: int, key: str, ttl_minutes: int) -> str:
    if type(user_id) is not int or not 1 <= user_id <= MAX_USER_ID:
        raise ValueError("User ID must be a positive signed BIGINT")
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "nbf": now,
            "exp": now + ttl_minutes * 60,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "token_use": "access",
        },
        key,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str, key: str) -> int:
    try:
        if len(token) > 4096:
            raise InvalidAccessToken
        claims = jwt.decode(
            token,
            key,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": REQUIRED_CLAIMS},
        )
        subject = claims["sub"]
        if (
            not isinstance(subject, str)
            or re.fullmatch(r"[1-9][0-9]{0,18}", subject) is None
            or int(subject) > MAX_USER_ID
            or claims["token_use"] != "access"
            or any(type(claims[name]) is not int for name in ("iat", "nbf", "exp"))
            or claims["nbf"] < claims["iat"]
            or not 0 < claims["exp"] - claims["iat"] <= 3600
        ):
            raise InvalidAccessToken
        return int(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise InvalidAccessToken from None
