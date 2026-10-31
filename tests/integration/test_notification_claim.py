"""Actual PostgreSQL/HTTP permission, privacy, rollback and overlapping writer tests."""

from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import event, update

from app.models import Settlement, User
from tests.integration.test_balances_api import client as client
from tests.integration.test_balances_api import get, headers
from tests.integration.test_by_items_storage import Harness
from tests.integration.test_by_items_storage import h as h
from tests.integration.test_settlements_api import body, contend, create, resolve, safe

pytestmark = pytest.mark.integration
RECIPIENT = 123456789


def setup_pending(h: Harness, client: TestClient) -> tuple[int, dict[str, Any]]:
    h.create()
    with h.db.sessions() as session, session.begin():
        session.execute(update(User).where(User.id == 10).values(telegram_id=RECIPIENT))
    payload = body()
    response = create(client, h, payload)
    assert response.status_code == 201, response.text
    return response.json()["settlement"]["id"], payload


def claim(client: TestClient, h: Harness, sid: int, *, actor: int = 20) -> Response:
    return cast(
        Response,
        client.post(
            f"/internal/settlements/{sid}/notification-claim",
            headers=headers(h, True, actor),
        ),
    )


def empty(response: Response) -> None:
    assert response.status_code == 204, response.text
    assert response.content == b"" and "content-type" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]


def business(client: TestClient, h: Harness) -> list[Any]:
    return [
        get(client, h, route)
        for route in ("settlements", "balances", "settlement-plan")
    ]


def test_correct_binding_exactly_once_lost_response_and_original_replay(
    h: Harness, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    sid, payload = setup_pending(h, client)
    before = business(client, h)
    original = create(client, h, payload).json()
    first = claim(client, h, sid)
    assert first.status_code == 200, first.text
    assert first.json() == {"recipient_telegram_id": RECIPIENT}
    assert RECIPIENT != original["settlement"]["receiver_id"]
    assert (
        first.headers["Cache-Control"] == "no-store" and first.headers["X-Request-ID"]
    )
    with h.db.sessions() as session:
        saved = session.get(Settlement, sid)
        assert saved is not None and saved.notification_claimed_at is not None
        stamp = saved.notification_claimed_at
    # The client may lose/ignore the committed first response; no second permission.
    assert create(client, h, payload).json() == original
    empty(claim(client, h, sid))
    with h.db.sessions() as session:
        saved = session.get(Settlement, sid)
        assert saved is not None and saved.notification_claimed_at == stamp
    assert business(client, h) == before
    for route in (f"/groups/{h.group}/members", f"/groups/{h.group}/settlements"):
        response = client.get(route, headers=headers(h))
        assert (
            "telegram" not in response.text
            and "notification_claimed_at" not in response.text
        )
    assert str(RECIPIENT) not in caplog.text


def test_no_binding_consumes_claim_even_if_receiver_links_later(
    h: Harness, client: TestClient
) -> None:
    sid, _ = setup_pending(h, client)
    with h.db.sessions() as session, session.begin():
        session.execute(
            update(User)
            .where(User.id == 10)
            .values(
                telegram_id=None,
                email="recipient@example.test",
                password_hash="$argon2id$fixture",
            )
        )
    before = business(client, h)
    empty(claim(client, h, sid))
    with h.db.sessions() as session, session.begin():
        row = session.get(Settlement, sid)
        assert row is not None and row.notification_claimed_at is not None
        stamp = row.notification_claimed_at
        session.execute(update(User).where(User.id == 10).values(telegram_id=RECIPIENT))
    empty(claim(client, h, sid))
    with h.db.sessions() as session:
        row = session.get(Settlement, sid)
        assert row is not None and row.notification_claimed_at == stamp
    assert business(client, h) == before


@pytest.mark.parametrize(
    "action,actor", [("confirm", 10), ("reject", 10), ("cancel", 20)]
)
def test_terminal_original_pending_replay_does_not_allow_notification(
    h: Harness, client: TestClient, action: str, actor: int
) -> None:
    sid, payload = setup_pending(h, client)
    original = create(client, h, payload).json()
    assert resolve(client, h, sid, action, actor=actor).status_code == 200
    before = business(client, h)
    assert create(client, h, payload).json() == original
    empty(claim(client, h, sid))
    assert business(client, h) == before
    with h.db.sessions() as session:
        row = session.get(Settlement, sid)
        assert row is not None and row.notification_claimed_at is None


@pytest.mark.parametrize("actor", [RECIPIENT, 30, 40, 50])
def test_wrong_sender_or_foreign_group_safe404_no_claim(
    h: Harness, client: TestClient, actor: int
) -> None:
    sid, _ = setup_pending(h, client)
    before = business(client, h)
    safe(claim(client, h, sid, actor=actor), 404, "settlement_not_found")
    safe(claim(client, h, 999999), 404, "settlement_not_found")
    assert business(client, h) == before
    with h.db.sessions() as session:
        row = session.get(Settlement, sid)
        assert row is not None and row.notification_claimed_at is None


def test_credentials_body_and_absent_public_endpoint(
    h: Harness, client: TestClient
) -> None:
    sid, _ = setup_pending(h, client)
    path = f"/internal/settlements/{sid}/notification-claim"
    for auth in ({}, headers(h, True) | {"X-Bot-Service-Token": "invalid"}):
        response = client.post(path, headers=auth)
        safe(response, 401, "invalid_service_token")
        assert response.headers["WWW-Authenticate"] == "BotService"
    safe(
        client.post(path, headers=headers(h) | headers(h, True)), 400, "ambiguous_actor"
    )
    safe(client.post(path, headers=headers(h)), 400, "ambiguous_actor")
    for payload in (
        {},
        {"sender_id": 20},
        {"receiver_id": 10},
        {"recipient_telegram_id": RECIPIENT},
    ):
        safe(
            client.post(path, headers=headers(h, True, 20), json=payload),
            400,
            "validation_error",
        )
    safe(
        client.post(
            "/internal/settlements/0/notification-claim", headers=headers(h, True, 20)
        ),
        400,
        "validation_error",
    )
    assert (
        client.post(
            f"/settlements/{sid}/notification-claim", headers=headers(h)
        ).status_code
        == 404
    )
    assert claim(client, h, sid).status_code == 200


def test_database_failure_rolls_back_claim_without_leaking(
    h: Harness, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    sid, _ = setup_pending(h, client)
    before = business(client, h)
    with h.db.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION fail_claim() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private marker'; END $$"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER fail_claim AFTER UPDATE ON settlements FOR EACH ROW EXECUTE FUNCTION fail_claim()"
        )
    response = claim(client, h, sid)
    safe(response, 500, "internal_error")
    assert str(RECIPIENT) not in response.text + caplog.text
    assert "private marker" not in response.text + caplog.text
    with h.db.sessions() as session:
        row = session.get(Settlement, sid)
        assert row is not None and row.notification_claimed_at is None
    assert business(client, h) == before


def test_two_http_claims_overlap_on_actual_group_lock(
    h: Harness, client: TestClient
) -> None:
    sid, _ = setup_pending(h, client)
    before = business(client, h)
    first, second = contend(
        client, h, lambda: claim(client, h, sid), lambda: claim(client, h, sid)
    )
    assert first.status_code == 200 and first.json() == {
        "recipient_telegram_id": RECIPIENT
    }
    empty(second)
    assert business(client, h) == before


@pytest.mark.parametrize("claim_first", [False, True])
def test_claim_vs_confirm_real_overlap_in_both_orders(
    h: Harness, client: TestClient, claim_first: bool
) -> None:
    sid, payload = setup_pending(h, client)
    original = create(client, h, payload).json()

    def claiming() -> Response:
        return claim(client, h, sid)

    def confirming() -> Response:
        return resolve(client, h, sid)

    first, second = contend(
        client,
        h,
        claiming if claim_first else confirming,
        confirming if claim_first else claiming,
    )
    if claim_first:
        assert first.status_code == 200 and first.json() == {
            "recipient_telegram_id": RECIPIENT
        }
        assert (
            second.status_code == 200
            and second.json()["settlement"]["status"] == "confirmed"
        )
    else:
        assert (
            first.status_code == 200
            and first.json()["settlement"]["status"] == "confirmed"
        )
        empty(second)
    assert create(client, h, payload).json() == original
    empty(claim(client, h, sid))
    balances = get(client, h, "balances")["balances"]
    assert [r["balance"] for r in balances] == ["1700.00", "-900.00", "-800.00"]
    with h.db.sessions() as session:
        row = session.get(Settlement, sid)
        assert (
            row is not None and (row.notification_claimed_at is not None) == claim_first
        )


def test_claim_uses_group_first_locks_and_constant_queries(
    h: Harness, client: TestClient
) -> None:
    sid, _ = setup_pending(h, client)
    # Actual request reads the binding after obtaining the group lock; an earlier
    # sender profile/user object cannot supply the receiver's Telegram ID.
    engine = cast(FastAPI, client.app).state.database.engine
    statements: list[str] = []

    def trace(*args: Any) -> None:
        statements.append(args[2])

    event.listen(engine, "after_cursor_execute", trace)
    try:
        assert claim(client, h, sid).json() == {"recipient_telegram_id": RECIPIENT}
    finally:
        event.remove(engine, "after_cursor_execute", trace)
    locks = [sql for sql in statements if "FOR UPDATE" in sql]
    assert (
        len(locks) == 2 and "FROM groups" in locks[0] and "FROM settlements" in locks[1]
    )
    assert len(statements) <= 9
