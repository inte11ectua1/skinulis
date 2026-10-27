"""High-entropy capability secrets, distinct from password hashing."""

import hashlib
import secrets
from datetime import UTC, datetime


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def secret_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)
