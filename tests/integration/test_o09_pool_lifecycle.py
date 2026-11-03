"""O-09: real pool lifecycle, detached actors and bounded concurrent finance reads."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.main import create_app
from tests.integration.test_balances_api import headers
from tests.integration.test_by_items_storage import Harness
from tests.integration.test_by_items_storage import h as h

pytestmark = pytest.mark.integration


@pytest.fixture
def bounded(h: Harness) -> Iterator[tuple[TestClient, Engine]]:
    h.create()
    application = create_app(h.settings)
    with TestClient(application) as client:
        database = application.state.database
        database.engine.dispose()
        # Stricter regression, not a performance tuning: even ONE slot suffices
        # if authentication returns its lease before the RR financial snapshot.
        engine = create_engine(
            h.settings.get_database_url(),
            pool_size=1,
            max_overflow=0,
            pool_timeout=3,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        )
        database.engine = engine
        database.sessions = sessionmaker(engine, expire_on_commit=False)
        yield client, engine


def pool(engine: Engine) -> QueuePool:
    assert isinstance(engine.pool, QueuePool)
    return engine.pool


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
def test_financial_read_reuses_released_auth_connection(
    h: Harness, bounded: tuple[TestClient, Engine], internal: bool, route: str
) -> None:
    client, engine = bounded
    prefix = "/internal" if internal else ""
    response = client.get(
        f"{prefix}/groups/{h.group}/{route}", headers=headers(h, internal)
    )
    assert response.status_code == 200, response.json()
    if route == "balances":
        assert [r["balance"] for r in response.json()["balances"]] == [
            "2200.00",
            "-1400.00",
            "-800.00",
        ]
    else:
        assert response.json()["transfers"] == [
            {"sender_id": 20, "receiver_id": 10, "amount": "1400.00"},
            {"sender_id": 30, "receiver_id": 10, "amount": "800.00"},
        ]
    assert pool(engine).checkedout() == 0


def test_parallel_balances_and_plan_do_not_starve_one_slot_pool(
    h: Harness, bounded: tuple[TestClient, Engine]
) -> None:
    client, engine = bounded
    barrier = Barrier(12)

    def read(index: int) -> Any:
        internal = bool(index % 4 // 2)
        route = "balances" if index % 2 == 0 else "settlement-plan"
        prefix = "/internal" if internal else ""
        barrier.wait(timeout=10)
        response = client.get(
            f"{prefix}/groups/{h.group}/{route}", headers=headers(h, internal)
        )
        assert response.status_code == 200, response.json()
        return response.json()

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(read, range(12)))
    assert len(results) == 12
    assert pool(engine).checkedout() == 0


@pytest.mark.parametrize("internal", [False, True])
def test_actor_is_loaded_detached_before_endpoint_needs_connection(
    h: Harness, bounded: tuple[TestClient, Engine], internal: bool
) -> None:
    from typing import Annotated

    from fastapi import Depends
    from sqlalchemy import inspect, text
    from sqlalchemy.orm import Session

    from app.api.dependencies import get_current_user
    from app.api.telegram_dependencies import get_bot_user
    from app.db import get_session
    from app.models import User
    from app.schemas.auth import UserProfile

    client, engine = bounded
    application = client.app
    assert isinstance(application, FastAPI)
    actor = get_bot_user if internal else get_current_user

    @application.get("/_o09/actor", response_model=UserProfile)
    def profile(
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> UserProfile:
        state = inspect(user)
        assert state.detached and not state.unloaded and not state.expired_attributes
        assert pool(engine).checkedout() == 0
        assert not session.in_transaction()
        # Hold the sole slot while serializing: an expired/lazy read cannot work.
        with session.begin():
            assert session.scalar(text("SELECT 1")) == 1
            return UserProfile.model_validate(user)

    response = client.get("/_o09/actor", headers=headers(h, internal))
    assert response.status_code == 200
    assert response.json()["id"] == 10
    assert set(response.json()) == {
        "id",
        "email",
        "telegram_id",
        "created_at",
        "display_name",
    }
    assert pool(engine).checkedout() == 0


@pytest.mark.parametrize("internal", [False, True])
def test_auth_never_closes_or_rolls_back_callers_pending_transaction(
    h: Harness, bounded: tuple[TestClient, Engine], internal: bool
) -> None:
    from typing import Annotated

    from fastapi import Depends
    from sqlalchemy.orm import Session

    from app.api.dependencies import get_current_user
    from app.api.telegram_dependencies import get_bot_user
    from app.db import get_session
    from app.models import User

    client, _ = bounded
    application = client.app
    assert isinstance(application, FastAPI)
    actor = get_bot_user if internal else get_current_user
    with h.db.sessions() as pending, pending.begin():
        marker = User(id=600, telegram_id=600)
        pending.add(marker)
        pending.flush()
        application.dependency_overrides[get_session] = lambda: pending

        @application.get("/_o09/pending")
        def endpoint(
            user: Annotated[User, Depends(actor)],
            session: Annotated[Session, Depends(get_session)],
        ) -> dict[str, int]:
            assert session is pending and session.in_transaction()
            assert session.get(User, 600) is marker
            return {"id": user.id}

        response = client.get("/_o09/pending", headers=headers(h, internal))
        assert response.status_code == 200 and response.json() == {"id": 10}
        assert pending.in_transaction()
    with h.db.sessions() as check:
        assert check.get(User, 600) is not None


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
def test_denied_actors_return_leases_without_granting_foreign_group_access(
    h: Harness, bounded: tuple[TestClient, Engine], internal: bool, route: str
) -> None:
    client, engine = bounded
    prefix = "/internal" if internal else ""
    path = f"{prefix}/groups/{h.group}/{route}"
    cases = [
        ({}, 401),
        (headers(h, internal, 40), 404),
        (headers(h, internal, 999), 404 if internal else 401),
        (headers(h, internal) | headers(h, not internal), 400),
        (headers(h, not internal), 400),
    ]
    for auth, expected in cases:
        response = client.get(path, headers=auth)
        assert response.status_code == expected, response.json()
        assert response.headers["Cache-Control"] == "no-store"
        assert set(response.json()) == {"error"}
        assert pool(engine).checkedout() == 0
    assert client.get(path, headers=headers(h, internal)).status_code == 200
    assert pool(engine).checkedout() == 0


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
def test_membership_integrity_and_ledger_still_share_read_only_rr_snapshot(
    h: Harness, bounded: tuple[TestClient, Engine], internal: bool, route: str
) -> None:
    from sqlalchemy import event

    client, engine = bounded
    observations: list[tuple[str, str, int, str]] = []
    seen: set[str] = set()

    def observe(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        many: bool,
    ) -> None:
        categories = ("FROM groups", "FROM group_members", "GROUP BY expenses.id")
        matched = [value for value in categories if value in statement]
        if not matched:
            return
        seen.update(matched)
        assert "FOR UPDATE" not in statement
        isolation = connection.exec_driver_sql(
            "SHOW transaction_isolation"
        ).scalar_one()
        readonly = connection.exec_driver_sql("SHOW transaction_read_only").scalar_one()
        snapshot = connection.exec_driver_sql(
            "SELECT pg_current_snapshot()::text"
        ).scalar_one()
        observations.append(
            (isolation, readonly, id(connection.get_transaction()), snapshot)
        )

    event.listen(engine, "after_cursor_execute", observe)
    try:
        prefix = "/internal" if internal else ""
        response = client.get(
            f"{prefix}/groups/{h.group}/{route}", headers=headers(h, internal)
        )
        assert response.status_code == 200
    finally:
        event.remove(engine, "after_cursor_execute", observe)
    assert seen == {"FROM groups", "FROM group_members", "GROUP BY expenses.id"}
    assert len(observations) >= 3 and len(set(observations)) == 1
    assert observations[0][:2] == ("repeatable read", "on")
    assert pool(engine).checkedout() == 0


@pytest.mark.parametrize("internal", [False, True])
def test_auth_query_exception_returns_lease_and_next_request_recovers(
    h: Harness, bounded: tuple[TestClient, Engine], internal: bool
) -> None:
    from sqlalchemy import event

    client, engine = bounded

    def fail_lookup(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        many: bool,
    ) -> None:
        if "FROM users" in statement:
            raise RuntimeError("synthetic-auth-failure-must-not-leak")

    event.listen(engine, "before_cursor_execute", fail_lookup)
    prefix = "/internal" if internal else ""
    path = f"{prefix}/groups/{h.group}/balances"
    try:
        response = client.get(path, headers=headers(h, internal))
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "synthetic-auth-failure" not in response.text
        assert pool(engine).checkedout() == 0
    finally:
        event.remove(engine, "before_cursor_execute", fail_lookup)
    assert client.get(path, headers=headers(h, internal)).status_code == 200
    assert pool(engine).checkedout() == 0
