"""O-08 adds mixed-history oracle, group isolation and financial JSON-log checks."""

import json
from concurrent.futures import ThreadPoolExecutor
from random import Random
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    ExpenseShare,
    Group,
    GroupMember,
    Settlement,
)
from tests.integration.test_balances_api import client as client
from tests.integration.test_balances_api import get, headers
from tests.integration.test_by_items_storage import Harness
from tests.integration.test_by_items_storage import h as h
from tests.integration.test_settlements_api import body, contend, create, resolve, safe

pytestmark = pytest.mark.integration


def allocate(amount: int, participants: list[int]) -> dict[int, int]:
    """Slow independent penny-by-penny oracle, never the production split code."""
    result = dict.fromkeys(sorted(participants), 0)
    ids = list(result)
    for penny in range(amount):
        result[ids[penny % len(ids)]] += 1
    return result


@pytest.mark.parametrize("seed", [6108, 7108])
def test_generated_persisted_history_matches_independent_ledger(
    h: Harness, client: TestClient, seed: int
) -> None:
    rng = Random(seed)
    expected = dict.fromkeys((10, 20, 30), 0)
    stored: list[tuple[int, int, dict[int, int], int]] = []
    for index in range(24):
        payer = rng.choice(list(expected))
        participants = rng.sample(list(expected), rng.randrange(1, 4))
        amount = rng.choice([1, 2, 10000, 999])
        shares = allocate(amount, participants)
        payload: dict[str, Any] = {
            "title": "O08 generated",
            "client_request_id": str(uuid4()),
        }
        if index % 3 == 0:
            payload.update(
                split_mode="equal",
                amount=f"{amount // 100}.{amount % 100:02d}",
                participants=participants,
            )
        elif index % 3 == 1:
            payload.update(
                split_mode="custom",
                amount=f"{amount // 100}.{amount % 100:02d}",
                shares=[
                    {"user_id": uid, "amount": f"{value // 100}.{value % 100:02d}"}
                    for uid, value in reversed(shares.items())
                ],
            )
        else:
            second = rng.sample(list(expected), rng.randrange(1, 4))
            extra = allocate(1, second)
            for uid, value in extra.items():
                shares[uid] = shares.get(uid, 0) + value
            payload.update(
                split_mode="by_items",
                items=[
                    {
                        "title": "First",
                        "amount": f"{amount // 100}.{amount % 100:02d}",
                        "participants": participants,
                    },
                    {"title": "Penny", "amount": "0.01", "participants": second},
                ],
            )
            amount += 1
        response = client.post(
            f"/groups/{h.group}/expenses", json=payload, headers=headers(h, actor=payer)
        )
        assert response.status_code == 201, response.text
        row = response.json()["expense"]
        assert sum(int(s["amount"].replace(".", "")) for s in row["shares"]) == amount
        assert {
            s["user_id"]: int(s["amount"].replace(".", "")) for s in row["shares"]
        } == shares
        stored.append((row["id"], payer, shares, amount))
        expected[payer] += amount
        for uid, value in shares.items():
            expected[uid] -= value
    # A new member changes membership only, never any historical share.
    with h.db.sessions() as session, session.begin():
        before = list(
            session.execute(
                select(
                    ExpenseShare.expense_id,
                    ExpenseShare.user_id,
                    ExpenseShare.amount_kopecks,
                ).order_by(ExpenseShare.expense_id, ExpenseShare.user_id)
            )
        )
        session.add(GroupMember(group_id=h.group, user_id=50, slot=4))
    expected[50] = 0
    for eid, payer, shares, amount in stored[::5]:
        assert (
            client.delete(
                f"/expenses/{eid}?expected_version=1", headers=headers(h, actor=payer)
            ).status_code
            == 200
        )
        expected[payer] -= amount
        for uid, value in shares.items():
            expected[uid] += value
    with h.db.sessions() as session:
        assert (
            list(
                session.execute(
                    select(
                        ExpenseShare.expense_id,
                        ExpenseShare.user_id,
                        ExpenseShare.amount_kopecks,
                    ).order_by(ExpenseShare.expense_id, ExpenseShare.user_id)
                )
            )
            == before
        )
    vector = get(client, h, "balances")["balances"]
    actual = {r["user_id"]: int(r["balance"].replace(".", "")) for r in vector}
    assert actual == expected and sum(actual.values()) == 0
    plan = get(client, h, "settlement-plan")
    remaining = actual.copy()
    for t in plan["transfers"]:
        amount = int(t["amount"].replace(".", ""))
        assert amount > 0
        remaining[t["sender_id"]] += amount
        remaining[t["receiver_id"]] -= amount
    assert set(remaining.values()) == {0}
    with h.db.sessions() as session:
        assert list(session.scalars(select(Settlement))) == []


@pytest.mark.parametrize("other_action,actor", [("reject", 10), ("cancel", 20)])
def test_confirm_wins_against_later_terminal_action_with_unchanged_timestamps(
    h: Harness, client: TestClient, other_action: str, actor: int
) -> None:
    h.create()
    original = create(client, h, body()).json()["settlement"]
    first, second = contend(
        client,
        h,
        lambda: resolve(client, h, original["id"]),
        lambda: resolve(client, h, original["id"], other_action, actor=actor),
    )
    assert first.status_code == 200
    safe(second, 409, "settlement_state_conflict")
    assert resolve(client, h, original["id"]).json() == first.json()
    for field in (
        "created_at",
        "client_request_id",
        "sender_id",
        "receiver_id",
        "amount",
    ):
        assert first.json()["settlement"][field] == original[field]


def test_locked_group_does_not_block_independent_group(
    h: Harness, client: TestClient
) -> None:
    with h.db.sessions() as session, session.begin():
        other = Group(owner_id=10, name="Independent", client_request_id=uuid4())
        session.add(other)
        session.flush()
        session.add(GroupMember(group_id=other.id, user_id=10, slot=1))
        other_id = other.id
    with h.db.sessions() as owner, owner.begin():
        owner.scalar(select(Group).where(Group.id == h.group).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                client.post,
                f"/groups/{other_id}/expenses",
                json={
                    "title": "Independent",
                    "amount": "0.01",
                    "split_mode": "equal",
                    "participants": [10],
                    "client_request_id": str(uuid4()),
                },
                headers=headers(h),
            )
            assert future.result(2).status_code == 201
            # Owner transaction still holds its lock while the other writer commits.
            assert owner.in_transaction()


def test_financial_failures_json_logs_do_not_disclose_payload_or_credentials(
    h: Harness, client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    h.create()
    sid = create(client, h, body()).json()["settlement"]["id"]
    private = "O08-private-financial-marker"
    auth = headers(h, actor=20)
    internal = headers(h, True, actor=20)
    responses = []
    capsys.readouterr()
    responses.append(
        client.post(
            f"/groups/{h.group}/expenses",
            json={
                "title": private,
                "amount": "123.456",
                "split_mode": "equal",
                "participants": [20],
                "client_request_id": str(uuid4()),
            },
            headers=auth,
        )
    )
    responses.append(client.post(f"/settlements/{sid}/confirm", headers=auth))
    responses.append(
        client.get(
            f"/internal/groups/{h.group}/balances",
            headers=internal | {"Authorization": auth["Authorization"]},
        )
    )
    responses.append(
        client.get(
            f"/internal/groups/{h.group}/balances",
            headers={"X-Bot-Service-Token": private, "X-Telegram-ID": "123456789"},
        )
    )
    responses.append(
        client.get(f"/groups/{h.group}/balances", headers=headers(h, actor=40))
    )
    # Actual corrupt ledger -> safe500 from the financial route, not a test endpoint.
    with h.db.sessions() as session, session.begin():
        row = session.scalar(select(ExpenseShare).limit(1))
        assert row is not None
        row.amount_kopecks += 1
    responses.append(client.get(f"/groups/{h.group}/balances", headers=auth))
    captured = capsys.readouterr()
    assert [r.status_code for r in responses] == [400, 403, 400, 401, 404, 500]
    logs = [json.loads(line) for line in captured.out.splitlines()]
    allowed = {
        "timestamp",
        "level",
        "service",
        "event",
        "request_id",
        "status",
        "method",
        "route",
        "duration_ms",
    }
    assert all(set(entry) <= allowed for entry in logs)
    serialized = captured.out + captured.err + "".join(r.text for r in responses)
    for marker in (
        private,
        "123.456",
        "123456789",
        auth["Authorization"].split()[1],
        internal["X-Bot-Service-Token"],
        "Traceback",
        "SELECT ",
        "amount_kopecks",
        "parameters",
    ):
        assert marker not in serialized
    for response in responses:
        request_id = response.headers["X-Request-ID"]
        assert str(UUID(request_id)) == request_id
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["error"]["request_id"] == request_id
        assert any(
            e["request_id"] == request_id and e.get("status") == response.status_code
            for e in logs
        )
    assert responses[3].headers["WWW-Authenticate"] == "BotService"
    with h.db.sessions() as session:
        pending = session.get(Settlement, sid)
        assert (
            pending is not None
            and pending.status == "pending"
            and pending.resolved_at is None
        )
