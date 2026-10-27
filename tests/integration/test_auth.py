import secrets
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import jwt
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.config import Settings
from app.core.migrate import main as migrate
from app.core.security import hash_password, verify_password
from app.main import create_app
from app.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
def client(database_url: URL) -> Iterator[TestClient]:
    assert migrate() == 0
    with TestClient(create_app(Settings(_env_file=None))) as instance:
        yield instance


@pytest.fixture
def password() -> str:
    return secrets.token_urlsafe(24)


def test_users_migration_and_metadata(database_url: URL) -> None:
    assert migrate() == 0 and migrate() == 0
    configuration = Config("alembic.ini")
    command.check(configuration)
    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        assert schema.get_pk_constraint("users")["name"] == "pk_users"
        columns = {column["name"]: column for column in schema.get_columns("users")}
        assert isinstance(columns["id"]["type"], BigInteger)
        assert not columns["id"]["nullable"]
        assert not columns["created_at"]["nullable"]
        assert columns["id"]["identity"]
        assert {c["name"] for c in schema.get_unique_constraints("users")} == {
            "uq_users_email",
            "uq_users_telegram_id",
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "values,constraint",
    [
        ({}, "ck_users_identity_present"),
        ({"email": "one@example.com"}, "ck_users_email_password_pair"),
        ({"password_hash": "$argon2id$unused"}, "ck_users_email_password_pair"),
        ({"telegram_id": -1}, "ck_users_telegram_id_positive"),
        ({"telegram_id": 0}, "ck_users_telegram_id_positive"),
        (
            {"email": "ONE@example.com", "password_hash": "$argon2id$unused"},
            "ck_users_email_normalized",
        ),
        (
            {"email": "", "password_hash": "$argon2id$unused"},
            "ck_users_email_normalized",
        ),
        (
            {"email": "one@example.com", "password_hash": secrets.token_urlsafe(24)},
            "ck_users_password_argon2id",
        ),
        ({"id": 0, "telegram_id": 123}, "ck_users_id_positive"),
    ],
)
def test_users_constraints_are_enforced_by_postgres(
    database_url: URL, values: dict[str, object], constraint: str
) -> None:
    assert migrate() == 0
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            with pytest.raises(IntegrityError) as caught, session.begin():
                session.add(User(**values))
                session.flush()
            assert caught.value.orig is not None
            # Access only structured diagnostics, never raw error args/SQL parameters.
            from psycopg import Error

            assert isinstance(caught.value.orig, Error)
            assert caught.value.orig.diag.constraint_name == constraint
            with session.begin():
                session.add(User(telegram_id=999))
            assert session.scalar(select(User.id)) is not None
    finally:
        engine.dispose()


def test_telegram_only_nullable_and_uniqueness(
    database_url: URL, password: str
) -> None:
    assert migrate() == 0
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            with session.begin():
                session.add_all([User(telegram_id=123), User(telegram_id=456)])
            for telegram_id in (123, 456):
                with pytest.raises(IntegrityError), session.begin():
                    session.add(User(telegram_id=telegram_id))
                    session.flush()
            with session.begin():
                session.add_all(
                    [
                        User(
                            email="a@example.com", password_hash=hash_password(password)
                        ),
                        User(
                            email="b@example.com", password_hash=hash_password(password)
                        ),
                    ]
                )
            with pytest.raises(IntegrityError), session.begin():
                session.add(
                    User(email="a@example.com", password_hash=hash_password(password))
                )
                session.flush()
            assert len(session.scalars(select(User)).all()) == 4
    finally:
        engine.dispose()


def test_register_login_me_and_no_actor_spoofing(
    client: TestClient,
    database_url: URL,
    password: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    profiles = []
    tokens = []
    for email in ("Alice@EXAMPLE.COM", "bob@example.com"):
        response = client.post(
            "/auth/register", json={"email": email, "password": password}
        )
        assert response.status_code == 201
        profile = response.json()
        profiles.append(profile)
        assert set(profile) == {"id", "email", "telegram_id", "created_at"}
        login = client.post(
            "/auth/login", json={"email": email.lower(), "password": password}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        tokens.append(token)
        me = client.get(
            "/users/me?user_id=999", headers={"Authorization": "Bearer " + token}
        )
        assert me.status_code == 200 and me.json() == profile
    assert profiles[0]["id"] != profiles[1]["id"]
    duplicate = client.post(
        "/auth/register", json={"email": " ALICE@example.com ", "password": password}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_already_registered"
    spoof = client.post(
        "/auth/register",
        json={
            "email": "new@example.com",
            "password": password,
            "user_id": profiles[1]["id"],
        },
    )
    assert spoof.status_code == 400
    first = client.get("/users/me", headers={"Authorization": "Bearer " + tokens[0]})
    assert first.json() == profiles[0]
    assert client.get("/users/me").status_code == 401
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            stored = session.get(User, profiles[0]["id"])
            assert stored is not None and stored.password_hash is not None
            assert verify_password(password, stored.password_hash)
            assert password not in stored.password_hash
            other = session.get(User, profiles[1]["id"])
            assert other is not None and other.email == "bob@example.com"
            session.delete(stored)
            session.commit()
        assert (
            client.get(
                "/users/me", headers={"Authorization": "Bearer " + tokens[0]}
            ).status_code
            == 401
        )
    finally:
        engine.dispose()
    for secret in [password, *tokens]:
        assert secret not in caplog.text


@pytest.mark.parametrize("kind", ["signature", "expired", "none", "missing_claim"])
def test_real_api_rejects_untrusted_jwt(
    client: TestClient, password: str, kind: str
) -> None:
    client.post(
        "/auth/register", json={"email": "alice@example.com", "password": password}
    )
    login = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": password}
    )
    token = login.json()["access_token"]
    settings = Settings(_env_file=None)
    key = settings.require_jwt_secret()
    claims = jwt.decode(token, key, algorithms=["HS256"], audience="skinulis-api")
    algorithm = "HS256"
    if kind == "signature":
        key = secrets.token_urlsafe(48)
    elif kind == "expired":
        claims["exp"] = 1
    elif kind == "none":
        key, algorithm = "", "none"
    else:
        del claims["sub"]
    forged = jwt.encode(claims, key, algorithm=algorithm)
    response = client.get("/users/me", headers={"Authorization": "Bearer " + forged})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
    assert forged not in response.text


def test_concurrent_registration_is_atomic(
    client: TestClient, database_url: URL, password: str
) -> None:
    barrier = Barrier(2)

    def register() -> int:
        barrier.wait(timeout=10)
        status = client.post(
            "/auth/register", json={"email": "race@example.com", "password": password}
        ).status_code
        assert isinstance(status, int)
        return status

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(register) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert sorted(results) == [201, 409]
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            assert (
                len(
                    session.scalars(
                        select(User).where(User.email == "race@example.com")
                    ).all()
                )
                == 1
            )
        response = client.post(
            "/auth/register",
            json={"email": "after-race@example.com", "password": password},
        )
        assert response.status_code == 201
    finally:
        engine.dispose()


def test_schema_supports_signed_bigint_fk_without_history_cascade(
    database_url: URL,
) -> None:
    assert migrate() == 0
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            user_id = connection.execute(
                text("INSERT INTO users (telegram_id) VALUES (123) RETURNING id")
            ).scalar_one()
            # Temporary probe only in the UUID test DB; no financial/group schema.
            connection.execute(
                text(
                    "CREATE TABLE fk_probe (user_id BIGINT REFERENCES users(id) ON DELETE RESTRICT)"
                )
            )
            connection.execute(
                text("INSERT INTO fk_probe VALUES (:id)"), {"id": user_id}
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT user_id FROM fk_probe")).scalar_one()
                == user_id
            )
    finally:
        engine.dispose()
