import secrets
from datetime import UTC, datetime

import jwt
import pytest
from argon2 import extract_parameters
from argon2.low_level import Type
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.core.security import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    REQUIRED_CLAIMS,
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import create_app
from app.schemas.auth import LoginInput, RegisterInput


@pytest.fixture
def key() -> str:
    return secrets.token_urlsafe(48)


@pytest.fixture
def password() -> str:
    return secrets.token_urlsafe(24)


def test_argon2id_hashes_are_salted_and_verify(password: str) -> None:
    one, two = hash_password(password), hash_password(password)
    assert one != two and password not in one
    params = extract_parameters(one)
    assert params.type == Type.ID
    assert (params.memory_cost, params.time_cost, params.parallelism) == (65536, 3, 4)
    assert params.salt_len == 16
    assert verify_password(password, one)
    assert verify_password(password, two)
    assert not verify_password(secrets.token_urlsafe(24), one)
    assert not verify_password(password, "corrupt hash")


def test_jwt_roundtrip_and_finite_lifetime(key: str) -> None:
    token = create_access_token(2**63 - 1, key, 15)
    assert decode_access_token(token, key) == 2**63 - 1
    claims = jwt.decode(token, key, algorithms=["HS256"], audience=JWT_AUDIENCE)
    assert set(REQUIRED_CLAIMS) <= claims.keys()
    assert claims["exp"] - claims["iat"] == 900
    assert claims["sub"] == str(2**63 - 1)
    assert "email" not in claims and "password" not in claims


def signed_claims(key: str, **changes: object) -> str:
    now = int(datetime.now(UTC).timestamp())
    payload: dict[str, object] = {
        "sub": "1",
        "iat": now,
        "nbf": now,
        "exp": now + 900,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "token_use": "access",
    }
    payload.update(changes)
    return jwt.encode(payload, key, algorithm="HS256")


@pytest.mark.parametrize("claim", REQUIRED_CLAIMS)
def test_each_required_jwt_claim_is_checked(key: str, claim: str) -> None:
    token = signed_claims(key)
    payload = jwt.decode(token, key, algorithms=["HS256"], audience=JWT_AUDIENCE)
    del payload[claim]
    with pytest.raises(InvalidAccessToken):
        decode_access_token(jwt.encode(payload, key, algorithm="HS256"), key)


@pytest.mark.parametrize(
    "changes",
    [
        {"sub": 1},
        {"sub": True},
        {"sub": "0"},
        {"sub": "-1"},
        {"sub": "01"},
        {"sub": str(2**63)},
        {"sub": "1.0"},
        {"sub": "other"},
        {"sub": "١"},
        {"sub": None},
        {"exp": 1},
        {"exp": "9999999999"},
        {"exp": True},
        {"iat": "1"},
        {"iat": False},
        {"nbf": "1"},
        {"iat": 9999999999},
        {"nbf": 9999999999},
        {"iss": "other"},
        {"aud": "other"},
        {"token_use": "refresh"},
    ],
)
def test_invalid_claim_types_and_values_are_rejected(
    key: str, changes: dict[str, object]
) -> None:
    with pytest.raises(InvalidAccessToken):
        decode_access_token(signed_claims(key, **changes), key)


@pytest.mark.parametrize("algorithm", ["HS384", "HS512", "none"])
def test_algorithm_is_fixed_not_controlled_by_header(key: str, algorithm: str) -> None:
    payload = jwt.decode(
        signed_claims(key), key, algorithms=["HS256"], audience=JWT_AUDIENCE
    )
    token = jwt.encode(payload, "" if algorithm == "none" else key, algorithm=algorithm)
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token, key)


@pytest.mark.parametrize("token", ["", "broken", "a.b.c", "x" * 4097])
def test_malformed_tokens_are_safe(key: str, token: str) -> None:
    with pytest.raises(InvalidAccessToken) as caught:
        decode_access_token(token, key)
    assert not str(caught.value)


def test_wrong_signature(key: str) -> None:
    with pytest.raises(InvalidAccessToken):
        decode_access_token(signed_claims(key), secrets.token_urlsafe(48))


@pytest.mark.parametrize("user_id", [0, -1, True, 2**63])
def test_cannot_issue_for_invalid_user_id(key: str, user_id: int) -> None:
    with pytest.raises(ValueError):
        create_access_token(user_id, key, 15)


@pytest.mark.parametrize(
    "email", ["wrong", "a@", "a b@example.com", "тест@example.com"]
)
def test_email_validation(email: str, password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterInput(email=email, password=SecretStr(password))


def test_email_normalization_and_password_is_not_modified(password: str) -> None:
    raw = " " + password + " "
    payload = RegisterInput(email=" Alice+Tag@EXAMPLE.COM ", password=SecretStr(raw))
    assert payload.email == "alice+tag@example.com"
    assert payload.password.get_secret_value() == raw
    assert raw not in repr(payload)


@pytest.mark.parametrize(
    "password", ["", "short", " " * 15, "x" * 129, "x" * 15 + "\x00"]
)
def test_registration_password_policy(password: str) -> None:
    with pytest.raises(ValidationError) as caught:
        RegisterInput(email="alice@example.com", password=SecretStr(password))
    assert "input_value" not in str(caught.value)


def test_credentials_reject_extra_actor_fields(password: str) -> None:
    with pytest.raises(ValidationError):
        LoginInput.model_validate(
            {"email": "alice@example.com", "password": password, "user_id": 2}
        )


def test_api_requires_key_but_migration_settings_do_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY")
    settings = Settings(
        _env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(24))
    )
    assert settings.get_database_url().password
    with pytest.raises(ValueError, match="Set JWT_SECRET_KEY"):
        create_app(settings)


def test_short_signing_key_is_hidden() -> None:
    short = secrets.token_urlsafe(8)
    settings = Settings(
        _env_file=None,
        postgres_password=SecretStr(secrets.token_urlsafe(24)),
        jwt_secret_key=SecretStr(short),
    )
    assert short not in repr(settings)
    with pytest.raises(ValueError) as caught:
        create_app(settings)
    assert short not in str(caught.value)


@pytest.mark.parametrize("ttl", [0, 61])
def test_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            postgres_password=SecretStr(secrets.token_urlsafe(24)),
            jwt_access_token_ttl_minutes=ttl,
        )
