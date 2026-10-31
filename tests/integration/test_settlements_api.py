"""O-07 on disposable PostgreSQL 17: real HTTP, independent writers and lock waits."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from time import monotonic, sleep
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import event, func, select, text, update

from app.models import ExpenseShare, GroupMember, Settlement
from app.services.expense_balances import calculate_balances
from app.services.expenses import CustomExpense
from app.services.money import format_money
from tests.integration.test_balances_api import client as client
from tests.integration.test_balances_api import get, headers
from tests.integration.test_by_items_storage import Harness
from tests.integration.test_by_items_storage import h as h

pytestmark = pytest.mark.integration


def body(amount: str = "500.00", receiver: int = 10) -> dict[str, Any]:
    return dict(receiver_id=receiver, amount=amount, client_request_id=str(uuid4()))


def create(
    client: TestClient,
    h: Harness,
    payload: dict[str, Any],
    *,
    actor: int = 20,
    internal: bool = False,
) -> Response:
    return cast(
        Response,
        client.post(
            ("/internal" if internal else "") + f"/groups/{h.group}/settlements",
            json=payload,
            headers=headers(h, internal, actor),
        ),
    )


def resolve(
    client: TestClient,
    h: Harness,
    sid: int,
    action: str = "confirm",
    *,
    actor: int = 10,
    internal: bool = False,
) -> Response:
    return cast(
        Response,
        client.post(
            ("/internal" if internal else "") + f"/settlements/{sid}/{action}",
            headers=headers(h, internal, actor),
        ),
    )


def safe(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert set(data) == {"error"} and set(data["error"]) == {
        "code",
        "message",
        "request_id",
    }
    assert data["error"]["code"] == code
    assert data["error"]["request_id"] == response.headers["X-Request-ID"]
    assert "private sentinel" not in response.text and "SELECT " not in response.text


def check(
    client: TestClient,
    h: Harness,
    amounts: list[str],
    transfers: list[tuple[int, int, str]],
) -> None:
    balances = get(client, h, "balances")["balances"]
    assert balances == [
        dict(user_id=u, balance=a) for u, a in zip((10, 20, 30), amounts, strict=True)
    ]
    assert sum(int(a.replace(".", "")) for a in amounts) == 0
    assert get(client, h, "settlement-plan")["transfers"] == [
        dict(sender_id=s, receiver_id=r, amount=a) for s, r, a in transfers
    ]


@pytest.mark.parametrize("internal", [False, True])
def test_restaurant_lifecycle_replay_and_reverse_debt(
    h: Harness, client: TestClient, internal: bool
) -> None:
    expense = h.create()
    payload = body()
    first = create(client, h, payload, internal=internal)
    assert first.status_code == 201, first.text
    original = first.json()
    row = original["settlement"]
    sid = row["id"]
    assert set(original) == {"settlement"}
    assert row["status"] == "pending" and row["resolved_at"] is None
    assert row["sender_id"] == 20 and row["created_at"].endswith("Z")
    assert (
        first.headers["Cache-Control"] == "no-store" and first.headers["X-Request-ID"]
    )
    # Simulate lost create response: same UUID is safe while still pending.
    assert create(client, h, payload, internal=internal).json() == original
    check(
        client,
        h,
        ["2200.00", "-1400.00", "-800.00"],
        [(20, 10, "1400.00"), (30, 10, "800.00")],
    )
    confirmed = resolve(client, h, sid, internal=internal)
    assert confirmed.status_code == 200, confirmed.text
    actual = confirmed.json()
    assert actual["settlement"]["status"] == "confirmed"
    assert actual["settlement"]["resolved_at"].endswith("Z")
    assert resolve(client, h, sid, internal=internal).json() == actual
    check(
        client,
        h,
        ["1700.00", "-900.00", "-800.00"],
        [(20, 10, "900.00"), (30, 10, "800.00")],
    )
    # Replay returns ORIGINAL pending, even though the remaining debt has changed.
    replay = create(client, h, payload, internal=internal)
    assert replay.status_code == 200 and replay.json() == original
    page = client.get(
        ("/internal" if internal else "") + f"/groups/{h.group}/settlements",
        headers=headers(h, internal),
    )
    assert page.json() == dict(items=[actual["settlement"]], limit=20, offset=0)
    deleted = client.delete(
        f"/expenses/{expense.id}?expected_version=1", headers=headers(h)
    )
    assert deleted.status_code == 200, deleted.text
    check(client, h, ["-500.00", "500.00", "0.00"], [(10, 20, "500.00")])
    assert create(client, h, payload, internal=internal).json() == original
    assert resolve(client, h, sid, internal=internal).json() == actual
    with h.db.sessions() as session:
        saved = session.get(Settlement, sid)
        assert saved is not None
        # Every immutable field survives transition, retry, expense delete.
        assert (
            saved.group_id,
            saved.sender_id,
            saved.receiver_id,
            saved.amount_kopecks,
            str(saved.client_request_id),
            saved.created_at.isoformat().replace("+00:00", "Z"),
        ) == (h.group, 20, 10, 50000, payload["client_request_id"], row["created_at"])
        assert session.scalar(select(func.count()).select_from(Settlement)) == 1


@pytest.mark.parametrize(
    "action,actor,status",
    [
        ("confirm", 10, "confirmed"),
        ("reject", 10, "rejected"),
        ("cancel", 20, "cancelled"),
    ],
)
@pytest.mark.parametrize("internal", [False, True])
def test_terminal_roles_repeats_replay_conflicts(
    h: Harness, client: TestClient, action: str, actor: int, status: str, internal: bool
) -> None:
    h.create()
    payload = body("1400.00")
    original = create(client, h, payload, internal=internal).json()
    sid = original["settlement"]["id"]
    for attempt in ("confirm", "reject", "cancel"):
        owner = 20 if attempt == "cancel" else 10
        for wrong in {10, 20, 30} - {owner}:
            safe(
                resolve(client, h, sid, attempt, actor=wrong, internal=internal),
                403,
                "settlement_sender_required"
                if attempt == "cancel"
                else "settlement_receiver_required",
            )
    result = resolve(client, h, sid, action, actor=actor, internal=internal)
    assert result.status_code == 200 and result.json()["settlement"]["status"] == status
    assert (
        resolve(client, h, sid, action, actor=actor, internal=internal).json()
        == result.json()
    )
    for attempt in ("confirm", "reject", "cancel"):
        owner = 20 if attempt == "cancel" else 10
        safe(
            resolve(client, h, sid, attempt, actor=30, internal=internal),
            403,
            "settlement_sender_required"
            if attempt == "cancel"
            else "settlement_receiver_required",
        )
        if attempt != action:
            safe(
                resolve(client, h, sid, attempt, actor=owner, internal=internal),
                409,
                "settlement_state_conflict",
            )
    replay = create(client, h, payload, internal=internal)
    assert replay.status_code == 200 and replay.json() == original
    assert get(client, h, "settlements")["items"] == [result.json()["settlement"]]
    for changed, sender in [
        (payload | {"amount": "0.01"}, 20),
        (payload | {"receiver_id": 30}, 20),
        (payload, 30),
    ]:
        safe(
            create(client, h, changed, actor=sender, internal=internal),
            409,
            "request_conflict",
        )
    if action != "confirm":
        check(
            client,
            h,
            ["2200.00", "-1400.00", "-800.00"],
            [(20, 10, "1400.00"), (30, 10, "800.00")],
        )


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"amount": "1400.01"}, "settlement_balance_conflict"),
        ({"amount": "0.00"}, "validation_error"),
        ({"amount": "-1.00"}, "validation_error"),
        ({"amount": "1e2"}, "validation_error"),
        ({"amount": 500}, "validation_error"),
        ({"receiver_id": 20}, "invalid_participants"),
        ({"receiver_id": 40}, "invalid_participants"),
        ({"receiver_id": 999999}, "invalid_participants"),
        ({"receiver_id": 30}, "settlement_balance_conflict"),
        ({"sender_id": 10}, "validation_error"),
        ({"client_request_id": "bad"}, "validation_error"),
    ],
)
def test_invalid_create_leaves_no_rows(
    h: Harness, client: TestClient, payload: dict[str, Any], code: str
) -> None:
    h.create()
    safe(
        create(client, h, body() | payload),
        409 if code == "settlement_balance_conflict" else 400,
        code,
    )
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Settlement)) == 0


@pytest.mark.parametrize("internal", [False, True])
def test_auth_hidden_resources_and_malformed_bodies(
    h: Harness, client: TestClient, internal: bool
) -> None:
    h.create()
    sid = create(client, h, body()).json()["settlement"]["id"]
    prefix = "/internal" if internal else ""
    paths = [
        ("post", f"{prefix}/groups/{h.group}/settlements", body()),
        ("get", f"{prefix}/groups/{h.group}/settlements", None),
    ] + [
        ("post", f"{prefix}/settlements/{sid}/{a}", {})
        for a in ("confirm", "reject", "cancel")
    ]
    for method, path, data in paths:
        for auth, status, code in [
            ({}, 401, "invalid_service_token" if internal else "invalid_token"),
            (
                headers(h, internal, 40),
                404,
                "settlement_not_found"
                if "/settlements/" in path
                else "group_not_found",
            ),
            (headers(h, internal) | headers(h, not internal), 400, "ambiguous_actor"),
        ]:
            r = client.request(method, path, json=data, headers=auth)
            safe(r, status, code)
            if status == 401:
                assert r.headers["WWW-Authenticate"] == (
                    "BotService" if internal else "Bearer"
                )
    for action in ("confirm", "reject", "cancel"):
        safe(
            resolve(client, h, 999999, action, internal=internal),
            404,
            "settlement_not_found",
        )
        safe(
            client.post(
                f"{prefix}/settlements/{sid}/{action}",
                json={"sender_id": 10},
                headers=headers(h, internal),
            ),
            400,
            "validation_error",
        )
    safe(
        client.post(
            f"{prefix}/groups/{h.group}/settlements",
            content="{",
            headers=headers(h, internal),
        ),
        400,
        "validation_error",
    )
    safe(
        client.get(f"{prefix}/groups/0/settlements", headers=headers(h, internal)),
        400,
        "validation_error",
    )


@pytest.mark.parametrize("change", ["put", "delete"])
def test_expense_changed_before_confirm_conflicts_without_resolving(
    h: Harness, client: TestClient, change: str
) -> None:
    expense = h.create()
    original = create(client, h, body("1400.00")).json()
    sid = original["settlement"]["id"]
    if change == "put":
        r = client.put(
            f"/expenses/{expense.id}",
            json=dict(
                title="Reduced",
                split_mode="custom",
                amount="600.00",
                shares=[dict(user_id=20, amount="600.00")],
                expected_version=1,
            ),
            headers=headers(h),
        )
    else:
        r = client.delete(
            f"/expenses/{expense.id}?expected_version=1", headers=headers(h)
        )
    assert r.status_code == 200, r.text
    before = get(client, h, "balances")
    safe(resolve(client, h, sid), 409, "settlement_balance_conflict")
    assert get(client, h, "settlements")["items"] == [original["settlement"]]
    assert get(client, h, "balances") == before


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "limit=x", "offset=-1", "status=bad", "direction=bad"],
)
def test_invalid_pagination(h: Harness, client: TestClient, query: str) -> None:
    safe(
        client.get(f"/groups/{h.group}/settlements?{query}", headers=headers(h)),
        400,
        "validation_error",
    )


def test_large_nonnegative_offset_returns_empty_page(
    h: Harness, client: TestClient
) -> None:
    offset = 2**80
    result = get(client, h, f"settlements?offset={offset}")
    assert result == dict(items=[], limit=20, offset=offset)


def test_filters_before_pagination_and_stable_created_id_order(
    h: Harness, client: TestClient
) -> None:
    h.create()
    assert get(client, h, "settlements") == dict(items=[], limit=20, offset=0)
    ids = [
        create(client, h, body("1.00"), actor=actor).json()["settlement"]["id"]
        for actor in (20, 30, 20, 30, 20)
    ]
    assert resolve(client, h, ids[0], "reject").status_code == 200
    assert resolve(client, h, ids[1], "cancel", actor=30).status_code == 200
    assert resolve(client, h, ids[2]).status_code == 200
    with h.db.sessions() as session, session.begin():
        # Explicit timestamp tie; direct fixture setup only, never an API edit.
        session.execute(
            update(Settlement).values(created_at=datetime(2026, 10, 30, tzinfo=UTC))
        )
    full = get(client, h, "settlements")["items"]
    assert [r["id"] for r in full] == ids
    assert all(r["created_at"] == "2026-10-30T00:00:00Z" for r in full)
    for internal in (False, True):
        prefix = "/internal" if internal else ""
        for actor in (10, 20, 30):
            for direction in ("incoming", "outgoing", "all"):
                for status in (None, "pending", "confirmed", "rejected", "cancelled"):
                    expected = [
                        r
                        for r in full
                        if (status is None or r["status"] == status)
                        and (
                            direction == "all"
                            or r[
                                "receiver_id"
                                if direction == "incoming"
                                else "sender_id"
                            ]
                            == actor
                        )
                    ]
                    for offset in (0, 1, 10):
                        params = dict(
                            direction=direction, limit="1", offset=str(offset)
                        )
                        if status:
                            params["status"] = status
                        response = client.get(
                            f"{prefix}/groups/{h.group}/settlements",
                            params=params,
                            headers=headers(h, internal, actor),
                        )
                        assert response.status_code == 200, response.text
                        assert response.json() == dict(
                            items=expected[offset : offset + 1], limit=1, offset=offset
                        )


@pytest.mark.parametrize("operation", ["create", "confirm", "reject", "cancel"])
def test_real_database_error_rolls_back_entire_mutation(
    h: Harness, client: TestClient, operation: str
) -> None:
    h.create()
    original = (
        None
        if operation == "create"
        else create(client, h, body()).json()["settlement"]
    )
    before = get(client, h, "balances")
    with h.db.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION fail_settlement() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private sentinel'; END $$"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER fail_settlement AFTER INSERT OR UPDATE ON settlements FOR EACH ROW EXECUTE FUNCTION fail_settlement()"
        )
    if original is None:
        response = create(client, h, body())
    else:
        response = resolve(
            client,
            h,
            original["id"],
            operation,
            actor=20 if operation == "cancel" else 10,
        )
    safe(response, 500, "internal_error")
    assert response.json()["error"]["message"] == "Internal server error"
    assert get(client, h, "settlements")["items"] == (
        [] if original is None else [original]
    )
    assert get(client, h, "balances") == before


def test_max_bigint_settlement_and_aggregate_above_bigint(
    h: Harness, client: TestClient
) -> None:
    maximum = 2**63 - 1
    with h.db.sessions() as session, session.begin():
        session.add_all(
            Settlement(
                group_id=h.group,
                sender_id=20,
                receiver_id=10,
                amount_kopecks=maximum,
                client_request_id=uuid4(),
                status="confirmed",
                created_at=datetime(2026, 10, 30, tzinfo=UTC),
                resolved_at=datetime.now(UTC),
            )
            for _ in range(3)
        )
    with h.db.sessions() as session:
        assert calculate_balances(session, h.group) == {
            10: -3 * maximum,
            20: 3 * maximum,
            30: 0,
        }
    payload = body(format_money(maximum), receiver=20)
    first = create(client, h, payload, actor=10)
    assert first.status_code == 201, first.text
    assert (
        resolve(client, h, first.json()["settlement"]["id"], actor=20).status_code
        == 200
    )
    with h.db.sessions() as session:
        assert calculate_balances(session, h.group) == {
            10: -2 * maximum,
            20: 2 * maximum,
            30: 0,
        }
    check(
        client,
        h,
        [format_money(-2 * maximum), format_money(2 * maximum), "0.00"],
        [(10, 20, format_money(2 * maximum))],
    )
    safe(
        create(client, h, body("92233720368547758.08", receiver=20), actor=10),
        400,
        "validation_error",
    )


def test_snapshot_corruption_does_not_create_or_confirm(
    h: Harness, client: TestClient
) -> None:
    expense = h.create()
    payload = body()
    original = create(client, h, payload).json()
    with h.db.sessions() as session, session.begin():
        session.execute(
            update(ExpenseShare)
            .where(ExpenseShare.expense_id == expense.id, ExpenseShare.user_id == 20)
            .values(amount_kopecks=1)
        )
    safe(create(client, h, body()), 500, "internal_error")
    safe(resolve(client, h, original["settlement"]["id"]), 500, "internal_error")
    assert get(client, h, "settlements")["items"] == [original["settlement"]]
    assert create(client, h, payload).json() == original


def test_replay_checks_membership_before_reading_original(
    h: Harness, client: TestClient
) -> None:
    h.create()
    payload = body()
    original = create(client, h, payload).json()
    safe(create(client, h, payload, actor=50), 404, "group_not_found")
    assert create(client, h, payload).json() == original


def test_group_owner_cannot_confirm_someone_elses_transfer(
    h: Harness, client: TestClient
) -> None:
    h.create(actor=20)
    response = create(client, h, body(receiver=20), actor=30)
    assert response.status_code == 201, response.text
    sid = response.json()["settlement"]["id"]
    safe(resolve(client, h, sid, actor=10), 403, "settlement_receiver_required")
    safe(
        resolve(client, h, sid, "reject", actor=10), 403, "settlement_receiver_required"
    )
    assert resolve(client, h, sid, actor=20).status_code == 200


def test_uuid_scope_is_group_and_operation_table(
    h: Harness, client: TestClient
) -> None:
    payload = body()
    from uuid import UUID

    key = UUID(payload["client_request_id"])
    h.create(key=key)
    first = create(client, h, payload)
    assert first.status_code == 201, first.text
    with h.db.sessions() as session, session.begin():
        session.add_all(
            GroupMember(group_id=h.other, user_id=uid, slot=n)
            for n, uid in enumerate((10, 20), 2)
        )
    h.create(
        CustomExpense("Other", "500.00", ((20, "500.00"),)), key=key, group=h.other
    )
    second = client.post(
        f"/groups/{h.other}/settlements", json=payload, headers=headers(h, actor=20)
    )
    assert (
        second.status_code == 201
        and second.json()["settlement"]["id"] != first.json()["settlement"]["id"]
    )
    assert len(get(client, h, "settlements")["items"]) == 1


def test_list_has_constant_query_count_and_no_write_locks(
    h: Harness, client: TestClient
) -> None:
    h.create()
    for _ in range(5):
        assert create(client, h, body()).status_code == 201
    engine = cast(FastAPI, client.app).state.database.engine
    statements: list[str] = []

    def trace(*args: Any) -> None:
        statements.append(args[2])

    event.listen(engine, "after_cursor_execute", trace)
    try:
        assert len(get(client, h, "settlements?limit=100")["items"]) == 5
    finally:
        event.remove(engine, "after_cursor_execute", trace)
    assert len(statements) <= 4
    assert not any("FOR UPDATE" in sql for sql in statements)


@pytest.mark.parametrize("route", ["balances", "settlement-plan"])
def test_mvcc_read_overlaps_confirm_without_mixed_ledger(
    h: Harness, client: TestClient, route: str
) -> None:
    h.create()
    sid = create(client, h, body()).json()["settlement"]["id"]
    before = get(client, h, route)
    paused, release = Event(), Event()
    engine = cast(FastAPI, client.app).state.database.engine

    def pause(*args: Any) -> None:
        # Only the read-only financial Session, not the confirm calculator.
        if not paused.is_set() and "GROUP BY expenses.id" in args[2]:
            connection = args[0]
            if connection.get_isolation_level() == "REPEATABLE READ":
                paused.set()
                assert release.wait(5)

    event.listen(engine, "after_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            reader = pool.submit(get, client, h, route)
            try:
                assert paused.wait(3)
                confirmed = resolve(client, h, sid)
                assert confirmed.status_code == 200, confirmed.text
                assert not reader.done()
            finally:
                release.set()
            assert reader.result(5) == before
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", pause)
    assert get(client, h, route) != before


def contend(
    client: TestClient,
    h: Harness,
    first: Callable[[], Response],
    second: Callable[[], Response],
) -> tuple[Response, Response]:
    """Pause actual first writer holding group lock; prove second waits on its PID."""
    engine = cast(FastAPI, client.app).state.database.engine
    locked, release = Event(), Event()
    owner: list[int] = []
    lock_sql: list[str] = []

    def pause(*args: Any) -> None:
        statement = args[2]
        if "FOR UPDATE" in statement:
            lock_sql.append(statement)
            if not owner:
                assert "FROM groups" in statement
                owner.append(args[0].connection.driver_connection.info.backend_pid)
                locked.set()
                assert release.wait(5), "Writer was not released"

    event.listen(engine, "after_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(first)
            try:
                assert locked.wait(3), "First writer did not acquire group lock"
                two = pool.submit(second)
                deadline = monotonic() + 2
                while True:
                    with h.db.engine.connect() as observer:
                        waiting = observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND :owner = ANY(pg_blocking_pids(pid))"
                            ),
                            {"owner": owner[0]},
                        )
                    if waiting:
                        break
                    assert monotonic() < deadline, (
                        "Second writer never waited on first writer's PostgreSQL lock"
                    )
                    sleep(0.01)
                assert not one.done() and not two.done()
            finally:
                release.set()
            result = one.result(10), two.result(10)
        assert len(lock_sql) >= 2 and "FROM groups" in lock_sql[0]
        return result
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", pause)


@pytest.mark.parametrize("same_intent", [False, True])
def test_concurrent_same_uuid_exactly_one_create(
    h: Harness, client: TestClient, same_intent: bool
) -> None:
    h.create()
    payload = body()
    other = payload if same_intent else payload | {"amount": "500.01"}
    first, second = contend(
        client, h, lambda: create(client, h, payload), lambda: create(client, h, other)
    )
    assert first.status_code == 201
    if same_intent:
        assert second.status_code == 200 and second.json() == first.json()
    else:
        safe(second, 409, "request_conflict")
    assert len(get(client, h, "settlements")["items"]) == 1


@pytest.mark.parametrize("same_row", [False, True])
def test_concurrent_confirm_no_overpay_or_double_effect(
    h: Harness, client: TestClient, same_row: bool
) -> None:
    h.create()
    sid = create(client, h, body("1400.00")).json()["settlement"]["id"]
    other = (
        sid
        if same_row
        else create(client, h, body("1400.00")).json()["settlement"]["id"]
    )
    first, second = contend(
        client, h, lambda: resolve(client, h, sid), lambda: resolve(client, h, other)
    )
    assert first.status_code == 200
    if same_row:
        assert second.status_code == 200 and first.json() == second.json()
    else:
        safe(second, 409, "settlement_balance_conflict")
    statuses = [r["status"] for r in get(client, h, "settlements")["items"]]
    assert statuses.count("confirmed") == 1
    assert statuses.count("pending") == (0 if same_row else 1)
    check(client, h, ["800.00", "0.00", "-800.00"], [(30, 10, "800.00")])


@pytest.mark.parametrize("other_action,actor", [("reject", 10), ("cancel", 20)])
def test_confirm_serializes_against_other_terminal_actions(
    h: Harness, client: TestClient, other_action: str, actor: int
) -> None:
    h.create()
    sid = create(client, h, body()).json()["settlement"]["id"]
    first, second = contend(
        client,
        h,
        lambda: resolve(client, h, sid, other_action, actor=actor),
        lambda: resolve(client, h, sid),
    )
    assert first.status_code == 200
    safe(second, 409, "settlement_state_conflict")
    assert get(client, h, "settlements")["items"] == [first.json()["settlement"]]
    check(
        client,
        h,
        ["2200.00", "-1400.00", "-800.00"],
        [(20, 10, "1400.00"), (30, 10, "800.00")],
    )


def test_sign_reversed_before_confirm_stays_pending(
    h: Harness, client: TestClient
) -> None:
    h.create()
    original = create(client, h, body()).json()["settlement"]
    h.create(CustomExpense("Opposite", "5000.00", ((10, "5000.00"),)), actor=20)
    safe(resolve(client, h, original["id"]), 409, "settlement_balance_conflict")
    assert get(client, h, "settlements")["items"] == [original]
    check(
        client,
        h,
        ["-2800.00", "3600.00", "-800.00"],
        [(10, 20, "2800.00"), (30, 20, "800.00")],
    )


def test_receiver_credit_can_limit_below_sender_debt(
    h: Harness, client: TestClient
) -> None:
    h.create(CustomExpense("First", "600.00", ((20, "600.00"),)))
    h.create(CustomExpense("Second", "400.00", ((20, "400.00"),)), actor=30)
    safe(create(client, h, body("600.01")), 409, "settlement_balance_conflict")
    created = create(client, h, body("600.00"))
    assert created.status_code == 201
    assert resolve(client, h, created.json()["settlement"]["id"]).status_code == 200
    check(client, h, ["0.00", "-400.00", "400.00"], [(20, 30, "400.00")])


@pytest.mark.parametrize("change", ["put", "delete"])
@pytest.mark.parametrize("confirm_first", [False, True])
def test_confirm_vs_expense_write_real_lock_overlap(
    h: Harness, client: TestClient, change: str, confirm_first: bool
) -> None:
    expense = h.create()
    sid = create(client, h, body("1400.00")).json()["settlement"]["id"]

    def edit() -> Response:
        if change == "delete":
            return cast(
                Response,
                client.delete(
                    f"/expenses/{expense.id}?expected_version=1", headers=headers(h)
                ),
            )
        return cast(
            Response,
            client.put(
                f"/expenses/{expense.id}",
                json=dict(
                    title="Reduced",
                    split_mode="custom",
                    amount="600.00",
                    shares=[dict(user_id=20, amount="600.00")],
                    expected_version=1,
                ),
                headers=headers(h),
            ),
        )

    def confirmation() -> Response:
        return resolve(client, h, sid)

    first, second = contend(
        client,
        h,
        confirmation if confirm_first else edit,
        edit if confirm_first else confirmation,
    )
    assert first.status_code == 200, first.text
    if confirm_first:
        assert second.status_code == 200, second.text
        debt = "1400.00" if change == "delete" else "800.00"
        check(client, h, ["-" + debt, debt, "0.00"], [(10, 20, debt)])
        assert get(client, h, "settlements")["items"][0]["status"] == "confirmed"
    else:
        safe(second, 409, "settlement_balance_conflict")
        assert get(client, h, "settlements")["items"][0]["status"] == "pending"
        remaining = "0.00" if change == "delete" else "600.00"
        check(
            client,
            h,
            [remaining, "0.00" if change == "delete" else "-600.00", "0.00"],
            [] if change == "delete" else [(20, 10, remaining)],
        )
