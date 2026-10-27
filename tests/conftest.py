"""Fresh in-memory signing key per test; never inherit an operator's JWT secret."""

import secrets

import pytest


@pytest.fixture(autouse=True)
def isolated_auth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_ACCESS_TOKEN_TTL_MINUTES", "15")
