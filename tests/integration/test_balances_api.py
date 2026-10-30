from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update

from app.core.security import create_access_token
from app.main import create_app
from app.models import ExpenseItemShare, ExpenseShare, GroupMember, Settlement
from app.services import expenses
from tests.integration.test_by_items_storage import Harness, penny
from tests.integration.test_by_items_storage import h as h

pytestmark = pytest.mark.integration


@pytest.fixture
def client(h: Harness) -> Iterator[TestClient]:
    with TestClient(create_app(h.settings)) as c:
        yield c


def headers(h: Harness, internal: bool = False, actor: int = 10) -> dict[str, str]:
    if internal:
        return {
            "X-Bot-Service-Token": h.settings.require_bot_service_token(),
            "X-Telegram-ID": str(actor),
        }
    return {
        "Authorization": "Bearer "
        + create_access_token(actor, h.settings.require_jwt_secret(), 15)
    }


def get(client: TestClient, h: Harness, route: str, internal: bool = False) -> Any:
    r = client.get(
        ("/internal" if internal else "") + f"/groups/{h.group}/" + route,
        headers=headers(h, internal),
    )
    assert r.status_code == 200, r.text
    assert r.headers["Cache-Control"] == "no-store"
    return r.json()


@pytest.mark.parametrize("internal", [False, True])
def test_restaurant_pending_confirmed_reverse(
    h: Harness, client: TestClient, internal: bool
) -> None:
    saved = h.create()

    def check(amounts: list[str], transfers: list[tuple[int, int, str]]) -> None:
        assert get(client, h, "balances", internal) == dict(
            group_id=h.group,
            balances=[
                dict(user_id=u, balance=b)
                for u, b in zip([10, 20, 30], amounts, strict=True)
            ],
        )
        assert get(client, h, "settlement-plan", internal) == dict(
            group_id=h.group,
            transfers=[
                dict(sender_id=s, receiver_id=r, amount=a) for s, r, a in transfers
            ],
        )

    check(["2200.00", "-1400.00", "-800.00"], [(20, 10, "1400.00"), (30, 10, "800.00")])
    with h.db.sessions() as session, session.begin():
        row = Settlement(
            group_id=h.group,
            sender_id=20,
            receiver_id=10,
            amount_kopecks=50000,
            status="pending",
            client_request_id=uuid4(),
        )
        session.add(row)
        session.flush()
        sid = row.id
    check(["2200.00", "-1400.00", "-800.00"], [(20, 10, "1400.00"), (30, 10, "800.00")])
    with h.db.sessions() as session, session.begin():
        session.execute(
            update(Settlement)
            .where(Settlement.id == sid)
            .values(status="confirmed", resolved_at=datetime.now(UTC))
        )
    check(["1700.00", "-900.00", "-800.00"], [(20, 10, "900.00"), (30, 10, "800.00")])
    with (
        h.db.sessions() as session,
        expenses.locked_edit(session, 10, saved.id) as editor,
    ):
        editor.mark_deleted()
    check(["-500.00", "500.00", "0.00"], [(10, 20, "500.00")])
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Settlement)) == 1


@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
@pytest.mark.parametrize("internal", [False, True])
def test_access_and_empty_group(
    h: Harness, client: TestClient, route: str, internal: bool
) -> None:
    prefix = "/internal" if internal else ""
    path = f"{prefix}/groups/{h.group}/{route}"
    assert get(client, h, route, internal)[
        "balances" if route == "balances" else "transfers"
    ] == (
        [dict(user_id=u, balance="0.00") for u in [10, 20, 30]]
        if route == "balances"
        else []
    )
    for auth, status in [
        ({}, 401),
        (headers(h, internal, 40), 404),
        (headers(h, internal) | headers(h, not internal), 400),
    ]:
        r = client.get(path, headers=auth)
        assert r.status_code == status and r.headers["Cache-Control"] == "no-store"
        assert set(r.json()) == {"error"}
    assert (
        client.get(
            f"{prefix}/groups/0/{route}", headers=headers(h, internal)
        ).status_code
        == 400
    )


@pytest.mark.parametrize("mode", ["equal", "custom", "by_items"])
def test_modes_new_member_and_zero_selections(
    h: Harness, client: TestClient, mode: str
) -> None:
    choices: dict[str, expenses.ExpenseInput] = {
        "equal": expenses.EqualExpense("Tea", "0.02", (10, 20, 30)),
        "custom": expenses.CustomExpense("Tea", "0.02", ((20, "0.02"), (30, "0.00"))),
        "by_items": penny(),
    }
    h.create(choices[mode])
    with h.db.sessions() as session, session.begin():
        session.add(GroupMember(group_id=h.group, user_id=50, slot=4))
    rows = get(client, h, "balances")["balances"]
    assert rows[-1] == dict(user_id=50, balance="0.00")
    assert [r["balance"] for r in rows] == (
        {
            "equal": ["0.01", "-0.01", "0.00", "0.00"],
            "custom": ["0.02", "-0.02", "0.00", "0.00"],
            "by_items": ["0.00", "0.00", "0.00", "0.00"],
        }[mode]
    )


@pytest.mark.parametrize("status", ["rejected", "cancelled", "confirmed"])
def test_large_numeric_and_ignored_states(
    h: Harness, client: TestClient, status: str
) -> None:
    with h.db.sessions() as session, session.begin():
        session.add_all(
            Settlement(
                group_id=h.group,
                sender_id=20,
                receiver_id=10,
                amount_kopecks=2**63 - 1,
                status=status,
                client_request_id=uuid4(),
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                resolved_at=datetime.now(UTC),
            )
            for _ in range(3)
        )
    rows = get(client, h, "balances")["balances"]
    from app.services.money import format_money

    value = 3 * (2**63 - 1) if status == "confirmed" else 0
    assert [r["balance"] for r in rows] == [
        format_money(-value),
        format_money(value),
        "0.00",
    ]
    if value:
        assert get(client, h, "settlement-plan")["transfers"] == [
            dict(sender_id=10, receiver_id=20, amount=format_money(value))
        ]


@pytest.mark.parametrize("detail", [False, True])
@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
def test_corruption_safe500(
    h: Harness, client: TestClient, detail: bool, route: str
) -> None:
    h.create()
    table = ExpenseItemShare if detail else ExpenseShare
    with h.db.sessions() as session, session.begin():
        session.execute(update(table).values(amount_kopecks=1))
    r = client.get(f"/groups/{h.group}/{route}", headers=headers(h))
    assert r.status_code == 500 and r.headers["Cache-Control"] == "no-store"
    assert r.json()["error"]["message"] == "Internal server error"


@pytest.mark.parametrize("action", ["put", "delete"])
@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
def test_repeatable_read_while_writer_commits(
    h: Harness, client: TestClient, action: str, route: str
) -> None:
    saved = h.create()
    old = get(client, h, route)
    paused = Event()
    release = Event()
    app: Any = client.app
    engine = app.state.database.engine
    statements: list[str] = []

    def hook(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        many: bool,
    ) -> None:
        statements.append(statement)
        if "GROUP BY expenses.id" in statement:
            assert (
                connection.exec_driver_sql("SHOW transaction_isolation").scalar()
                == "repeatable read"
            )
            assert (
                connection.exec_driver_sql("SHOW transaction_read_only").scalar()
                == "on"
            )
            paused.set()
            assert release.wait(10)

    event.listen(engine, "after_cursor_execute", hook)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(get, client, h, route)
            assert paused.wait(10)
            # A real independent writer commits AFTER reader's first financial SELECT.
            with (
                h.db.sessions() as session,
                expenses.locked_edit(session, 10, saved.id) as editor,
            ):
                if action == "delete":
                    editor.mark_deleted()
                else:
                    editor.replace_snapshot(penny(), allow_receipt=True)
            release.set()
            assert pending.result(10) == old
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", hook)
    assert get(client, h, route) != old
    assert not any("FOR UPDATE" in s for s in statements)
    assert len(statements) < 15
