"""Actual PostgreSQL parameter/driver failures stay private at the HTTP boundary."""

import json
import secrets
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.migrate import main as migrate
from app.db import get_session
from app.main import create_app

pytestmark = pytest.mark.integration


def test_postgres_failure_and_auth_chain_have_safe_correlated_logs(
    database_url: URL, capsys: pytest.CaptureFixture[str]
) -> None:
    assert migrate() == 0
    app = create_app(Settings(_env_file=None))
    private = secrets.token_urlsafe(32)

    @app.get("/test/database-error")
    def database_error(session: Annotated[Session, Depends(get_session)]) -> None:
        session.execute(text("SELECT CAST(:private AS BIGINT)"), {"private": private})

    with TestClient(app) as client:
        capsys.readouterr()
        error = client.get("/test/database-error?secret=" + private)
        assert error.status_code == 500
        captured = capsys.readouterr()
        entries = [json.loads(line) for line in captured.out.splitlines()]
        assert not captured.err
        assert {entry["event"] for entry in entries} == {
            "http_request_failed",
            "http_request_completed",
        }
        assert all(
            entry["request_id"] == error.headers["X-Request-ID"] for entry in entries
        )
        assert private not in json.dumps(entries) + error.text
        # Failed request rolls back/closes its session; later requests still work.
        assert client.get("/health").status_code == 200
        password = secrets.token_urlsafe(32)
        payload = {"email": "logging@example.com", "password": password}
        assert client.post("/auth/register", json=payload).status_code == 201
        assert client.post("/auth/register", json=payload).status_code == 409
        login = client.post("/auth/login", json=payload)
        token = login.json()["access_token"]
        assert (
            client.get(
                "/users/me", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 200
        )
        captured = capsys.readouterr()
        assert password not in captured.out + captured.err
        assert token not in captured.out + captured.err
        assert "logging@example.com" not in captured.out + captured.err
        assert all(json.loads(line)["request_id"] for line in captured.out.splitlines())
