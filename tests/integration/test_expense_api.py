"""Approved HTTP Expense contract on real disposable PostgreSQL 17."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Barrier
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.migrate import main as migrate
from app.core.security import create_access_token
from app.db import Database
from app.main import create_app
from app.models import Expense, ExpenseShare, Group, GroupMember, Settlement, User

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 28, 10, tzinfo=UTC)


@dataclass
class API:
    client: TestClient
    db: Database
    settings: Settings
    group: int
    other: int

    def headers(self, actor: int = 2, internal: bool = False) -> dict[str, str]:
        if internal:
            return {
                "X-Bot-Service-Token": self.settings.require_bot_service_token(),
                "X-Telegram-ID": str(actor * 100),
            }
        return {
            "Authorization": "Bearer "
            + create_access_token(actor, self.settings.require_jwt_secret(), 15)
        }

    def create(
        self,
        payload: dict[str, Any] | None = None,
        *,
        actor: int = 2,
        internal: bool = False,
        group: int | None = None,
    ) -> httpx.Response:
        path = f"/groups/{self.group if group is None else group}/expenses"
        result: httpx.Response = self.client.post(
            ("/internal" if internal else "") + path,
            json=equal() if payload is None else payload,
            headers=self.headers(actor, internal),
        )
        return result


def equal(amount: str = "100.00") -> dict[str, Any]:
    return dict(
        title=" Обед ",
        split_mode="equal",
        amount=amount,
        participants=[5, 2, 1],
        client_request_id=str(uuid4()),
    )


def put(amount: str = "1.00", version: int = 1) -> dict[str, Any]:
    return dict(
        title="Чай",
        split_mode="custom",
        amount=amount,
        shares=[dict(user_id=5, amount=amount)],
        expected_version=version,
    )


def error(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.fixture
def a(database_url: URL) -> Iterator[API]:
    assert migrate() == 0
    settings = Settings(_env_file=None)
    app = create_app(settings)
    with TestClient(app) as client:
        db: Database = app.state.database
        with db.sessions() as session, session.begin():
            session.add_all(
                User(id=uid, telegram_id=uid * 100) for uid in (1, 2, 5, 10, 20)
            )
            session.flush()
            group = Group(owner_id=1, name="Trip", client_request_id=uuid4())
            other = Group(owner_id=10, name="Other", client_request_id=uuid4())
            session.add_all([group, other])
            session.flush()
            session.add_all(
                GroupMember(group_id=group.id, user_id=uid, slot=n)
                for n, uid in enumerate((1, 2, 5), 1)
            )
            session.add(GroupMember(group_id=other.id, user_id=10, slot=1))
            result = API(client, db, settings, group.id, other.id)
        yield result


@pytest.mark.parametrize("internal", [False, True])
def test_complete_crud_preview_original_replay_and_versions(
    a: API, internal: bool
) -> None:
    prefix = "/internal" if internal else ""
    headers = a.headers(internal=internal)
    payload = equal("0.01")
    preview_payload = {
        key: value for key, value in payload.items() if key != "client_request_id"
    }
    preview = a.client.post(
        f"{prefix}/groups/{a.group}/expenses/preview",
        json=preview_payload,
        headers=headers,
    )
    assert preview.status_code == 200
    assert preview.json() == dict(
        group_id=a.group,
        payer_id=2,
        split_mode="equal",
        title="Обед",
        amount="0.01",
        shares=[
            dict(user_id=1, amount="0.01"),
            dict(user_id=2, amount="0.00"),
            dict(user_id=5, amount="0.00"),
        ],
    )
    with a.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 0
    created = a.create(payload, internal=internal)
    assert created.status_code == 201 and created.headers["Cache-Control"] == "no-store"
    initial = created.json()
    assert set(initial) == {"expense", "balances"} and initial["balances"] is None
    expense = initial["expense"]
    assert set(expense) == {
        "id",
        "group_id",
        "payer_id",
        "client_request_id",
        "split_mode",
        "title",
        "amount",
        "shares",
        "created_at",
        "deleted_at",
        "version",
    }
    assert expense["payer_id"] == 2 and expense["version"] == 1
    assert expense["created_at"].endswith("Z")
    eid = expense["id"]
    assert a.client.get(f"{prefix}/expenses/{eid}", headers=headers).json() == expense
    equivalent = payload | {"title": "\u2003Обед\u00a0", "participants": [1, 5, 2]}
    replay = a.create(equivalent, internal=internal)
    assert replay.status_code == 200 and replay.json() == initial
    changed = a.client.put(f"{prefix}/expenses/{eid}", json=put(), headers=headers)
    assert changed.status_code == 200
    assert changed.json()["expense"]["version"] == 2
    assert changed.json()["expense"]["split_mode"] == "custom"
    assert changed.json()["expense"]["shares"] == [dict(user_id=5, amount="1.00")]
    assert a.create(payload, internal=internal).json() == initial
    error(
        a.client.put(f"{prefix}/expenses/{eid}", json=put(), headers=headers),
        409,
        "expense_version_conflict",
    )
    error(
        a.client.delete(f"{prefix}/expenses/{eid}?expected_version=1", headers=headers),
        409,
        "expense_version_conflict",
    )
    deleted = a.client.delete(
        f"{prefix}/expenses/{eid}?expected_version=2", headers=headers
    )
    assert deleted.status_code == 200
    assert deleted.json()["expense"]["version"] == 3
    assert deleted.json()["expense"]["deleted_at"].endswith("Z")
    assert (
        a.client.delete(
            f"{prefix}/expenses/{eid}?expected_version=1", headers=headers
        ).json()
        == deleted.json()
    )
    error(
        a.client.get(f"{prefix}/expenses/{eid}", headers=headers),
        404,
        "expense_not_found",
    )
    error(
        a.client.put(f"{prefix}/expenses/{eid}", json=put(version=3), headers=headers),
        404,
        "expense_not_found",
    )
    assert a.create(payload, internal=internal).json() == initial
    assert a.client.get(
        f"{prefix}/groups/{a.group}/expenses", headers=headers
    ).json() == {"items": [], "limit": 20, "offset": 0}
    with a.db.sessions() as session:
        saved = session.get(Expense, eid)
        assert saved is not None and saved.initial_create_result == initial
        assert saved.initial_create_intent is not None
        assert saved.initial_create_intent["participants"] == [1, 2, 5]
        assert saved.initial_create_intent["amount_kopecks"] == 1
        assert list(
            session.execute(
                select(ExpenseShare.user_id, ExpenseShare.amount_kopecks).where(
                    ExpenseShare.expense_id == eid
                )
            )
        ) == [(5, 100)]


@pytest.mark.parametrize("internal", [False, True])
def test_permissions_spoofing_and_no_foreign_disclosure(a: API, internal: bool) -> None:
    prefix = "/internal" if internal else ""
    saved = a.create(internal=internal).json()["expense"]
    eid = saved["id"]
    for actor in (1, 5):
        headers = a.headers(actor, internal)
        error(
            a.client.put(f"{prefix}/expenses/{eid}", json=put(), headers=headers),
            403,
            "expense_author_required",
        )
        error(
            a.client.delete(
                f"{prefix}/expenses/{eid}?expected_version=1", headers=headers
            ),
            403,
            "expense_author_required",
        )
    for eid_guess in (eid, 2**62):
        headers = a.headers(10, internal)
        error(
            a.client.get(f"{prefix}/expenses/{eid_guess}", headers=headers),
            404,
            "expense_not_found",
        )
        error(
            a.client.put(f"{prefix}/expenses/{eid_guess}", json=put(), headers=headers),
            404,
            "expense_not_found",
        )
        error(
            a.client.delete(
                f"{prefix}/expenses/{eid_guess}?expected_version=1", headers=headers
            ),
            404,
            "expense_not_found",
        )
    for gid in (a.other, 2**62):
        error(a.create(group=gid, internal=internal), 404, "group_not_found")
        error(
            a.client.get(
                f"{prefix}/groups/{gid}/expenses", headers=a.headers(internal=internal)
            ),
            404,
            "group_not_found",
        )
    for field in ("payer_id", "author_id", "telegram_id", "group_id"):
        error(
            a.create(equal() | {field: 1}, internal=internal), 400, "validation_error"
        )
    error(
        a.create(equal() | {"participants": [10]}, internal=internal),
        400,
        "invalid_participants",
    )
    error(
        a.create(equal() | {"participants": [999]}, internal=internal),
        400,
        "invalid_participants",
    )
    assert (
        a.client.get(
            f"{prefix}/expenses/{eid}", headers=a.headers(internal=internal)
        ).json()
        == saved
    )


def test_jwt_service_channel_credentials_and_missing_auth(a: API) -> None:
    payload = equal()
    path = f"/groups/{a.group}/expenses"
    error(a.client.post(path, json=payload), 401, "invalid_token")
    error(
        a.client.post(path, json=payload, headers={"Authorization": "Bearer invalid"}),
        401,
        "invalid_token",
    )
    error(
        a.client.post(path, json=payload, headers=a.headers(999)), 401, "invalid_token"
    )
    mixed = a.headers() | a.headers(internal=True)
    error(a.client.post(path, json=payload, headers=mixed), 400, "ambiguous_actor")
    error(
        a.client.post("/internal" + path, json=payload, headers=mixed),
        400,
        "ambiguous_actor",
    )
    error(
        a.client.post(path, json=payload, headers=a.headers(internal=True)),
        400,
        "ambiguous_actor",
    )
    error(
        a.client.post(
            "/internal" + path,
            json=payload,
            headers={"X-Bot-Service-Token": "invalid", "X-Telegram-ID": "200"},
        ),
        401,
        "invalid_service_token",
    )
    error(
        a.client.post("/internal" + path, json=payload, headers=a.headers(999, True)),
        404,
        "telegram_profile_not_found",
    )
    with a.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 0


def test_custom_sum_conflicts_intent_scope_and_actor_binding(a: API) -> None:
    payload: dict[str, Any] = dict(
        title=" e\u0301 ",
        split_mode="custom",
        amount="100.00",
        shares=[
            dict(user_id=1, amount="0.00"),
            dict(user_id=2, amount="40.00"),
            dict(user_id=5, amount="60.00"),
        ],
        client_request_id=str(uuid4()),
    )
    first = a.create(payload)
    assert first.status_code == 201
    initial = first.json()
    reordered = payload | {"title": "é", "shares": list(reversed(payload["shares"]))}
    assert a.create(reordered).json() == initial
    for amount in ("59.99", "60.01"):
        bad = deepcopy(payload)
        bad["client_request_id"] = str(uuid4())
        bad["shares"][2]["amount"] = amount
        error(a.create(bad), 400, "validation_error")
    changed = payload | {
        "amount": "101.00",
        "shares": [dict(user_id=5, amount="101.00")],
    }
    error(a.create(changed), 409, "request_conflict")
    error(a.create(payload, actor=1), 409, "request_conflict")
    error(
        a.create(equal() | {"client_request_id": payload["client_request_id"]}),
        409,
        "request_conflict",
    )
    other = a.create(
        equal()
        | {"participants": [10], "client_request_id": payload["client_request_id"]},
        actor=10,
        group=a.other,
    )
    assert other.status_code == 201
    with a.db.sessions() as session:
        saved = session.get(Expense, initial["expense"]["id"])
        assert saved is not None
        intent = deepcopy(saved.initial_create_intent)
        assert intent is not None and intent["shares"] == [[1, 0], [2, 4000], [5, 6000]]


def test_legacy_request_has_no_fabricated_original_history(a: API) -> None:
    key = uuid4()
    with a.db.sessions() as session, session.begin():
        session.add(
            Expense(
                group_id=a.group,
                payer_id=2,
                title="Legacy",
                split_mode="equal",
                amount_kopecks=100,
                client_request_id=key,
            )
        )
    error(
        a.create(equal("1.00") | {"client_request_id": str(key)}),
        409,
        "request_history_unavailable",
    )
    error(
        a.create(equal("1.00") | {"client_request_id": str(key)}, actor=1),
        409,
        "request_conflict",
    )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?expected_version=0",
        "?expected_version=1.0",
        "?expected_version=true",
        "?expected_version=-1",
    ],
)
def test_delete_requires_integer_version(a: API, query: str) -> None:
    eid = a.create().json()["expense"]["id"]
    error(
        a.client.delete(f"/expenses/{eid}{query}", headers=a.headers()),
        400,
        "validation_error",
    )


def test_preview_validation_and_final_post_recheck_membership(a: API) -> None:
    payload = equal()
    eid_key = payload.pop("client_request_id")
    extras: tuple[dict[str, Any], ...] = (
        {"client_request_id": eid_key},
        {"expected_version": 1},
        {"items": []},
    )
    for extra in extras:
        error(
            a.client.post(
                f"/groups/{a.group}/expenses/preview",
                json=payload | extra,
                headers=a.headers(),
            ),
            400,
            "validation_error",
        )
    headers = a.headers()
    assert (
        a.client.post(
            f"/groups/{a.group}/expenses/preview", json=payload, headers=headers
        ).status_code
        == 200
    )
    # An unreferenced consumer can be removed via privileged test SQL; preview
    # did not reserve its membership. Production membership deletion is not an API.
    with a.db.sessions() as session, session.begin():
        session.execute(
            text("DELETE FROM group_members WHERE group_id=:gid AND user_id=5"),
            {"gid": a.group},
        )
    error(
        a.create(payload | {"client_request_id": eid_key}), 400, "invalid_participants"
    )
    with a.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 0


def test_page_snapshots_order_and_new_members(a: API) -> None:
    saved = [a.create().json()["expense"] for _ in range(23)]
    with a.db.sessions() as session, session.begin():
        session.execute(update(Expense).values(created_at=NOW))
        session.add(GroupMember(group_id=a.group, user_id=20, slot=4))
    headers = a.headers(20)
    page = a.client.get(f"/groups/{a.group}/expenses", headers=headers).json()
    assert set(page) == {"items", "limit", "offset"}
    assert len(page["items"]) == 20
    assert [item["id"] for item in page["items"]] == [item["id"] for item in saved[:20]]
    last = a.client.get(
        f"/groups/{a.group}/expenses?limit=20&offset=20", headers=headers
    ).json()
    assert [item["id"] for item in last["items"]] == [item["id"] for item in saved[20:]]
    assert all(
        item["shares"] == saved[0]["shares"]
        for item in [*page["items"], *last["items"]]
    )
    for query in ("limit=0", "limit=101", "offset=-1"):
        error(
            a.client.get(f"/groups/{a.group}/expenses?{query}", headers=headers),
            400,
            "validation_error",
        )


def confirmed(a: API, amount: int = 5000) -> int:
    with a.db.sessions() as session, session.begin():
        settlement = Settlement(
            group_id=a.group,
            sender_id=5,
            receiver_id=2,
            amount_kopecks=amount,
            status="confirmed",
            client_request_id=uuid4(),
            created_at=NOW,
            resolved_at=NOW,
        )
        session.add(settlement)
        session.flush()
        return settlement.id


def test_confirmed_balances_exact_on_create_update_delete_and_original_replay(
    a: API,
) -> None:
    sid = confirmed(a)
    payload = equal() | {"participants": [5]}
    original = a.create(payload).json()
    assert original["balances"] == [
        dict(user_id=1, balance="0.00"),
        dict(user_id=2, balance="50.00"),
        dict(user_id=5, balance="-50.00"),
    ]
    eid = original["expense"]["id"]
    changed = a.client.put(
        f"/expenses/{eid}", json=put("30.00"), headers=a.headers()
    ).json()
    assert changed["balances"] == [
        dict(user_id=1, balance="0.00"),
        dict(user_id=2, balance="-20.00"),
        dict(user_id=5, balance="20.00"),
    ]
    deleted = a.client.delete(
        f"/expenses/{eid}?expected_version=2", headers=a.headers()
    ).json()
    assert deleted["balances"] == [
        dict(user_id=1, balance="0.00"),
        dict(user_id=2, balance="-50.00"),
        dict(user_id=5, balance="50.00"),
    ]
    confirmed(a, 100)
    repeated = a.client.delete(
        f"/expenses/{eid}?expected_version=1", headers=a.headers()
    ).json()
    assert repeated["expense"] == deleted["expense"]
    assert repeated["balances"][1]["balance"] == "-51.00"
    assert a.create(payload).json() == original  # Original envelope, not new balances.
    with a.db.sessions() as session:
        settlement = session.get(Settlement, sid)
        assert (
            settlement is not None
            and settlement.amount_kopecks == 5000
            and settlement.status == "confirmed"
        )


def test_balances_use_numeric_before_arithmetic_and_ignore_unconfirmed(a: API) -> None:
    for _ in range(2):
        confirmed(a, 2**63 - 1)
    with a.db.sessions() as session, session.begin():
        for status in ("pending", "rejected", "cancelled"):
            session.add(
                Settlement(
                    group_id=a.group,
                    sender_id=5,
                    receiver_id=2,
                    amount_kopecks=100,
                    status=status,
                    client_request_id=uuid4(),
                    created_at=NOW,
                    resolved_at=None if status == "pending" else NOW,
                )
            )
    result = a.create(equal("0.01") | {"participants": [5]}).json()
    assert result["balances"] == [
        dict(user_id=1, balance="0.00"),
        dict(user_id=2, balance="-184467440737095516.13"),
        dict(user_id=5, balance="184467440737095516.13"),
    ]


def test_corrupted_history_causes_safe_500_and_rolls_back_new_write(
    a: API, caplog: pytest.LogCaptureFixture
) -> None:
    confirmed(a)
    eid = a.create().json()["expense"]["id"]
    with a.db.sessions() as session, session.begin():
        session.execute(
            update(ExpenseShare)
            .where(ExpenseShare.expense_id == eid)
            .values(amount_kopecks=0)
        )
    payload = equal() | {"title": "PRIVATE-EXPENSE-TITLE"}
    response = a.create(payload)
    error(response, 500, "internal_error")
    assert "PRIVATE-EXPENSE-TITLE" not in response.text + caplog.text
    with a.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
    error(a.client.get(f"/expenses/{eid}", headers=a.headers()), 500, "internal_error")


def test_actual_mid_update_constraint_failure_rolls_back_http_version_and_history(
    a: API,
) -> None:
    initial = a.create().json()["expense"]
    eid = initial["id"]

    def invalid_share(session: Session, flush_context: Any, instances: Any) -> None:
        if any(isinstance(row, ExpenseShare) for row in session.new):
            for row in session.new:
                if isinstance(row, ExpenseShare):
                    row.amount_kopecks = -1

    event.listen(Session, "before_flush", invalid_share)
    try:
        error(
            a.client.put(f"/expenses/{eid}", json=put(), headers=a.headers()),
            500,
            "internal_error",
        )
    finally:
        event.remove(Session, "before_flush", invalid_share)
    assert a.client.get(f"/expenses/{eid}", headers=a.headers()).json() == initial


def overlap(
    a: API, actions: list[Callable[[], httpx.Response]]
) -> list[httpx.Response]:
    barrier = Barrier(len(actions) + 1)

    def run(action: Callable[[], httpx.Response]) -> httpx.Response:
        barrier.wait(timeout=10)
        return action()

    with (
        ThreadPoolExecutor(max_workers=len(actions)) as pool,
        a.db.engine.connect() as blocker,
    ):
        transaction = blocker.begin()
        blocker.execute(select(Group).where(Group.id == a.group).with_for_update())
        futures = [pool.submit(run, action) for action in actions]
        barrier.wait(timeout=10)
        try:
            deadline = monotonic() + 2
            while True:
                with a.db.engine.connect() as observer:
                    waiting = observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock'"
                        )
                    )
                if waiting is not None and waiting >= len(actions):
                    break
                assert monotonic() < deadline, (
                    "HTTP workers did not overlap at a DB lock"
                )
                sleep(0.01)
        finally:
            transaction.rollback()
        return [future.result(timeout=10) for future in futures]


@pytest.mark.parametrize("different", [False, True])
def test_overlapping_posts_replay_or_conflict_without_duplicate(
    a: API, different: bool
) -> None:
    payload = equal()
    second = payload | (
        {"amount": "101.00"} if different else {"participants": [1, 2, 5]}
    )
    responses = overlap(a, [lambda: a.create(payload), lambda: a.create(second)])
    assert sorted(response.status_code for response in responses) == (
        [201, 409] if different else [200, 201]
    )
    if not different:
        assert responses[0].json() == responses[1].json()
    else:
        error(
            next(response for response in responses if response.status_code == 409),
            409,
            "request_conflict",
        )
    with a.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1


def test_overlapping_puts_have_one_stale_conflict(a: API) -> None:
    eid = a.create().json()["expense"]["id"]
    headers = a.headers()
    responses = overlap(
        a,
        [
            lambda: a.client.put(f"/expenses/{eid}", json=put("1.00"), headers=headers),
            lambda: a.client.put(f"/expenses/{eid}", json=put("2.00"), headers=headers),
        ],
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    error(
        next(response for response in responses if response.status_code == 409),
        409,
        "expense_version_conflict",
    )
    result = a.client.get(f"/expenses/{eid}", headers=headers).json()
    assert result["version"] == 2 and result["amount"] in ("1.00", "2.00")
    assert result["shares"] == [dict(user_id=5, amount=result["amount"])]


def test_overlapping_put_delete_and_double_delete(a: API) -> None:
    eid = a.create().json()["expense"]["id"]
    headers = a.headers()
    responses = overlap(
        a,
        [
            lambda: a.client.put(f"/expenses/{eid}", json=put(), headers=headers),
            lambda: a.client.delete(
                f"/expenses/{eid}?expected_version=1", headers=headers
            ),
        ],
    )
    assert sorted(response.status_code for response in responses) in (
        [200, 404],
        [200, 409],
    )
    current = a.client.get(f"/expenses/{eid}", headers=headers)
    if current.status_code == 200:
        version = current.json()["version"]
    else:
        version = 1
    repeated = overlap(
        a,
        [
            lambda: a.client.delete(
                f"/expenses/{eid}?expected_version={version}", headers=headers
            ),
            lambda: a.client.delete(
                f"/expenses/{eid}?expected_version={version}", headers=headers
            ),
        ],
    )
    assert all(response.status_code == 200 for response in repeated)
    assert repeated[0].json() == repeated[1].json()


@pytest.mark.parametrize(
    ("amount", "shares", "kopecks"),
    [
        ("0.01", ["0.01", "0.00", "0.00"], 1),
        ("100.00", ["33.34", "33.33", "33.33"], 10000),
        ("1000000.00", ["333333.34", "333333.33", "333333.33"], 100000000),
    ],
)
def test_http_equal_exact_bounds_and_saved_shares(
    a: API, amount: str, shares: list[str], kopecks: int
) -> None:
    response = a.create(equal(amount))
    assert response.status_code == 201
    expense = response.json()["expense"]
    assert [row["amount"] for row in expense["shares"]] == shares
    with a.db.sessions() as session:
        assert (
            session.scalar(
                select(func.sum(ExpenseShare.amount_kopecks)).where(
                    ExpenseShare.expense_id == expense["id"]
                )
            )
            == kopecks
        )


def test_custom_to_equal_and_original_history_is_immutable(a: API) -> None:
    initial = a.create().json()
    eid = initial["expense"]["id"]
    headers = a.headers()
    assert (
        a.client.put(f"/expenses/{eid}", json=put(), headers=headers).status_code == 200
    )
    replacement = equal("0.01")
    replacement.pop("client_request_id")
    response = a.client.put(
        f"/expenses/{eid}", json=replacement | {"expected_version": 2}, headers=headers
    )
    assert response.status_code == 200 and response.json()["expense"]["version"] == 3
    assert response.json()["expense"]["shares"] == [
        dict(user_id=1, amount="0.01"),
        dict(user_id=2, amount="0.00"),
        dict(user_id=5, amount="0.00"),
    ]
    with a.db.sessions() as session:
        record = session.get(Expense, eid)
        assert record is not None and record.initial_create_result == initial
        for field in ("initial_create_result", "initial_create_intent"):
            with pytest.raises(ValueError, match="immutable"):
                setattr(record, field, None)


@pytest.mark.parametrize("internal", [False, True])
def test_each_expense_operation_requires_its_verified_actor(
    a: API, internal: bool
) -> None:
    eid = a.create().json()["expense"]["id"]
    prefix = "/internal" if internal else ""
    operations: list[tuple[str, str, dict[str, Any] | None]] = [
        ("POST", f"/groups/{a.group}/expenses", equal()),
        (
            "POST",
            f"/groups/{a.group}/expenses/preview",
            {
                key: value
                for key, value in equal().items()
                if key != "client_request_id"
            },
        ),
        ("GET", f"/groups/{a.group}/expenses", None),
        ("GET", f"/expenses/{eid}", None),
        ("PUT", f"/expenses/{eid}", put()),
        ("DELETE", f"/expenses/{eid}?expected_version=1", None),
    ]
    for method, path, payload in operations:
        error(
            a.client.request(method, prefix + path, json=payload),
            401,
            "invalid_service_token" if internal else "invalid_token",
        )


def test_http_invalid_money_unicode_and_mode_fields_leave_no_rows(a: API) -> None:
    invalids: list[dict[str, Any]] = [
        {"amount": 100},
        {"amount": "1.0"},
        {"amount": " 1.00"},
        {"amount": "-0.00"},
        {"amount": "1000000.01"},
        {"title": " \u2003 "},
        {"title": "👩\u200d💻"},
        {"title": "a" * 121},
        {"shares": []},
        {"items": []},
    ]
    for changes in invalids:
        error(a.create(equal() | changes), 400, "validation_error")
    with a.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 0


def test_other_group_confirmed_does_not_leak_into_mutation_balances(a: API) -> None:
    with a.db.sessions() as session, session.begin():
        session.add(GroupMember(group_id=a.other, user_id=20, slot=2))
        session.flush()
        session.add(
            Settlement(
                group_id=a.other,
                sender_id=20,
                receiver_id=10,
                amount_kopecks=100,
                status="confirmed",
                client_request_id=uuid4(),
                created_at=NOW,
                resolved_at=NOW,
            )
        )
    assert a.create().json()["balances"] is None


def test_http_group_first_locks_and_read_only_preview(a: API) -> None:
    sql: list[str] = []

    def capture(*args: Any) -> None:
        sql.append(args[2])

    event.listen(a.db.engine, "before_cursor_execute", capture)
    try:
        payload = equal()
        preview = {
            key: value for key, value in payload.items() if key != "client_request_id"
        }
        assert (
            a.client.post(
                f"/groups/{a.group}/expenses/preview", json=preview, headers=a.headers()
            ).status_code
            == 200
        )
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in sql)
        sql.clear()
        eid = a.create(payload).json()["expense"]["id"]
        locks = [statement.lower() for statement in sql if "FOR UPDATE" in statement]
        assert len(locks) == 1 and "from groups" in locks[0]
        for method, suffix, body in (
            ("PUT", "", put()),
            ("DELETE", "?expected_version=2", None),
        ):
            sql.clear()
            response = a.client.request(
                method, f"/expenses/{eid}{suffix}", json=body, headers=a.headers()
            )
            assert response.status_code == 200
            locks = [
                statement.lower() for statement in sql if "FOR UPDATE" in statement
            ]
            assert (
                len(locks) == 2
                and "from groups" in locks[0]
                and "from expenses" in locks[1]
            )
    finally:
        event.remove(a.db.engine, "before_cursor_execute", capture)


def test_page_offset_beyond_bigint_is_empty_not_an_overflow(a: API) -> None:
    response = a.client.get(
        f"/groups/{a.group}/expenses?offset={2**63}", headers=a.headers()
    )
    assert response.status_code == 200 and response.json()["items"] == []


def test_wire_dates_remain_utc_when_database_session_timezone_differs(a: API) -> None:
    def timezone(connection: Any, record: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Europe/Moscow'")
        connection.commit()

    a.db.engine.dispose()
    event.listen(a.db.engine, "connect", timezone)
    try:
        original = a.create().json()
        eid = original["expense"]["id"]
        assert original["expense"]["created_at"].endswith("Z")
        result = a.client.get(f"/expenses/{eid}", headers=a.headers())
        assert result.json() == original["expense"]
        deleted = a.client.delete(
            f"/expenses/{eid}?expected_version=1", headers=a.headers()
        ).json()
        assert deleted["expense"]["deleted_at"].endswith("Z")
    finally:
        event.remove(a.db.engine, "connect", timezone)
