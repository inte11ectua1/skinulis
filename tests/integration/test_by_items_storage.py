"""Real O-05 storage/read primitives; pending wire/replay decisions are not API acceptance."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Barrier, Event
from time import monotonic, sleep
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.migrate import main as migrate
from app.core.security import create_access_token
from app.db import Database
from app.main import create_app
from app.models import (
    Expense,
    ExpenseItem,
    ExpenseItemShare,
    ExpenseShare,
    Group,
    GroupMember,
    Settlement,
    User,
)
from app.services import expenses
from app.services.expense_balances import mutation_balances
from app.services.expenses import (
    ByItemsExpense,
    CustomExpense,
    EqualExpense,
    ExpenseInput,
    ExpenseSnapshot,
    ReceiptItemInput,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 28, 10, tzinfo=UTC)


def restaurant() -> ByItemsExpense:
    return ByItemsExpense(
        "Ресторан",
        (
            ReceiptItemInput("Паста", "700.00", (10,)),
            ReceiptItemInput("Стейк", "1100.00", (20,)),
            ReceiptItemInput("Салат", "500.00", (30,)),
            ReceiptItemInput("Пицца", "900.00", (30, 10, 20)),
        ),
    )


def penny() -> ByItemsExpense:
    return ByItemsExpense(
        "Копейки",
        (
            ReceiptItemInput("Чай", "0.01", (10, 20, 30)),
            ReceiptItemInput("Сбор", "0.01", (30, 20, 10)),
        ),
    )


@dataclass
class Harness:
    db: Database
    settings: Settings
    group: int
    other: int

    def create(
        self,
        draft: ExpenseInput | None = None,
        *,
        key: UUID | None = None,
        actor: int = 10,
        group: int | None = None,
    ) -> ExpenseSnapshot:
        with self.db.sessions() as session:
            return expenses.create_once(
                session,
                self.group if group is None else group,
                actor,
                uuid4() if key is None else key,
                restaurant() if draft is None else draft,
            )

    def read(self, eid: int, actor: int = 10) -> ExpenseSnapshot:
        with self.db.sessions() as session:
            return expenses.read_expense(session, actor, eid)


@pytest.fixture
def h(database_url: URL) -> Iterator[Harness]:
    assert migrate() == 0
    settings = Settings(_env_file=None)
    db = Database(settings)
    try:
        with db.sessions() as session, session.begin():
            session.add_all(
                User(id=uid, telegram_id=uid) for uid in (10, 20, 30, 40, 50)
            )
            session.flush()
            group = Group(owner_id=10, name="Trip", client_request_id=uuid4())
            other = Group(owner_id=40, name="Other", client_request_id=uuid4())
            session.add_all([group, other])
            session.flush()
            session.add_all(
                GroupMember(group_id=group.id, user_id=uid, slot=n)
                for n, uid in enumerate((10, 20, 30), 1)
            )
            session.add(GroupMember(group_id=other.id, user_id=40, slot=1))
            result = Harness(db, settings, group.id, other.id)
        yield result
    finally:
        db.close()


def test_restaurant_saves_all_four_levels_and_returns_stored_details(
    h: Harness,
) -> None:
    saved = h.create()
    assert saved.amount_kopecks == 320000
    assert saved.shares == ((10, 100000), (20, 140000), (30, 80000))
    assert [item.position for item in saved.items] == [1, 2, 3, 4]
    assert saved.items[-1].shares == ((10, 30000), (20, 30000), (30, 30000))
    assert h.read(saved.id) == saved
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
        assert session.scalar(select(func.count()).select_from(ExpenseItem)) == 4
        assert session.scalar(select(func.count()).select_from(ExpenseShare)) == 3
        assert session.scalar(select(func.count()).select_from(ExpenseItemShare)) == 6
        assert session.scalar(select(func.sum(ExpenseItem.amount_kopecks))) == 320000


def test_selected_zero_rows_and_new_members_never_recalculate_history(
    h: Harness,
) -> None:
    saved = h.create(penny())
    assert saved.shares == ((10, 2), (20, 0), (30, 0))
    with h.db.sessions() as session, session.begin():
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExpenseShare)
                .where(ExpenseShare.amount_kopecks == 0)
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ExpenseItemShare)
                .where(ExpenseItemShare.amount_kopecks == 0)
            )
            == 4
        )
        session.add(GroupMember(group_id=h.group, user_id=50, slot=4))
    assert h.read(saved.id, 50) == saved
    assert all(item.shares == ((10, 1), (20, 0), (30, 0)) for item in saved.items)


@pytest.mark.parametrize("old_mode", ["equal", "custom", "by_items"])
@pytest.mark.parametrize("new_mode", ["equal", "custom", "by_items"])
def test_explicit_storage_transition_opt_in_replaces_children_atomically(
    h: Harness, old_mode: str, new_mode: str
) -> None:
    choices: dict[str, ExpenseInput] = {
        "equal": EqualExpense("Обед", "1.00", (20,)),
        "custom": CustomExpense("Обед", "1.00", ((30, "1.00"),)),
        "by_items": restaurant(),
    }
    saved = h.create(choices[old_mode])
    old_ids = {item.id for item in saved.items}
    with (
        h.db.sessions() as session,
        expenses.locked_edit(session, 10, saved.id) as editor,
    ):
        changed = editor.replace_snapshot(choices[new_mode], allow_receipt=True)
    assert h.read(saved.id) == changed
    assert changed.split_mode == new_mode
    assert (
        changed.id == saved.id and changed.client_request_id == saved.client_request_id
    )
    assert sum(amount for _, amount in changed.shares) == changed.amount_kopecks
    assert not old_ids.intersection(item.id for item in changed.items)
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ExpenseItem)) == (
            4 if new_mode == "by_items" else 0
        )
        assert session.scalar(select(func.count()).select_from(ExpenseItemShare)) == (
            6 if new_mode == "by_items" else 0
        )


def test_constraint_failure_after_old_children_deleted_restores_entire_receipt(
    h: Harness,
) -> None:
    saved = h.create()
    with h.db.sessions() as session:

        def fail_second_item(
            session_value: Session, context: Any, instances: Any
        ) -> None:
            shares = [
                value
                for value in session_value.new
                if isinstance(value, ExpenseItemShare)
            ]
            if shares:
                max(shares, key=lambda value: value.item_id).amount_kopecks = -1

        event.listen(session, "before_flush", fail_second_item)
        try:
            with pytest.raises(IntegrityError):
                with expenses.locked_edit(session, 10, saved.id) as editor:
                    editor.replace_snapshot(penny(), allow_receipt=True)
            assert not session.in_transaction()
        finally:
            event.remove(session, "before_flush", fail_second_item)
    assert h.read(saved.id) == saved  # Includes old item IDs, positions and all shares.


def test_invalid_middle_item_and_foreign_consumers_leave_whole_old_snapshot(
    h: Harness,
) -> None:
    saved = h.create()
    for bad in (
        ReceiptItemInput("Bad", "0.00", (10,)),
        ReceiptItemInput("Bad", "1.00", (40,)),
        ReceiptItemInput("👩\u200d💻", "1.00", (10,)),
    ):
        draft = ByItemsExpense("New", (penny().items[0], bad, penny().items[1]))
        with h.db.sessions() as session, pytest.raises(ValueError):
            with expenses.locked_edit(session, 10, saved.id) as editor:
                editor.replace_snapshot(draft, allow_receipt=True)
        assert h.read(saved.id) == saved


def test_membership_author_and_composite_item_group_fk_are_preserved(
    h: Harness,
) -> None:
    saved = h.create(actor=20)
    with h.db.sessions() as session, pytest.raises(expenses.ExpenseAuthorRequired):
        with expenses.locked_edit(session, 10, saved.id) as editor:
            editor.replace_snapshot(penny(), allow_receipt=True)
    with pytest.raises(expenses.ExpenseNotFound):
        h.read(saved.id, actor=40)
    other = h.create(
        ByItemsExpense("Other", (ReceiptItemInput("Tea", "1.00", (40,)),)),
        actor=40,
        group=h.other,
    )
    with h.db.sessions() as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            ExpenseItemShare(
                item_id=saved.items[0].id,
                expense_id=other.id,
                group_id=h.other,
                user_id=40,
                amount_kopecks=1,
            )
        )
    assert h.read(saved.id) == saved


def test_confirmed_balances_use_final_shares_once_and_soft_delete_keeps_history(
    h: Harness,
) -> None:
    saved = h.create()
    with h.db.sessions() as session, session.begin():
        settlement = Settlement(
            group_id=h.group,
            sender_id=20,
            receiver_id=10,
            amount_kopecks=50000,
            status="confirmed",
            client_request_id=uuid4(),
            created_at=NOW,
            resolved_at=NOW,
        )
        session.add(settlement)
        session.flush()
        sid = settlement.id
    with h.db.sessions() as session:
        balances = mutation_balances(session, h.group)
        assert balances is not None
        assert [(row.user_id, row.balance) for row in balances] == [
            (10, "1700.00"),
            (20, "-900.00"),
            (30, "-800.00"),
        ]
        session.rollback()
        with expenses.locked_edit(session, 10, saved.id) as editor:
            deleted = editor.mark_deleted()
        with expenses.locked_edit(
            session, 10, saved.id, include_deleted=True
        ) as editor:
            assert editor.mark_deleted() == deleted
        assert deleted.items == saved.items and deleted.shares == saved.shares
        balances = mutation_balances(session, h.group)
        assert balances is not None
        assert [(row.user_id, row.balance) for row in balances] == [
            (10, "-500.00"),
            (20, "500.00"),
            (30, "0.00"),
        ]
        stored_settlement = session.get(Settlement, sid)
        assert (
            stored_settlement is not None
            and stored_settlement.amount_kopecks == 50000
            and stored_settlement.status == "confirmed"
        )
        assert session.scalar(select(func.count()).select_from(ExpenseItem)) == 4
        assert session.scalar(select(func.count()).select_from(ExpenseItemShare)) == 6


@pytest.mark.parametrize(
    "corruption", ["item_sum", "missing_zero", "final_mismatch", "missing_items"]
)
def test_corrupt_receipt_is_rejected_without_repair(
    h: Harness, corruption: str
) -> None:
    saved = h.create(penny())
    with h.db.sessions() as session, session.begin():
        if corruption == "item_sum":
            session.execute(
                update(ExpenseItemShare)
                .where(
                    ExpenseItemShare.item_id == saved.items[0].id,
                    ExpenseItemShare.user_id == 10,
                )
                .values(amount_kopecks=2)
            )
        elif corruption == "missing_zero":
            session.execute(
                delete(ExpenseItemShare).where(ExpenseItemShare.user_id == 30)
            )
        elif corruption == "final_mismatch":
            session.execute(
                update(ExpenseShare)
                .where(ExpenseShare.user_id == 10)
                .values(amount_kopecks=1)
            )
            session.execute(
                update(ExpenseShare)
                .where(ExpenseShare.user_id == 20)
                .values(amount_kopecks=1)
            )
        else:
            session.execute(delete(ExpenseItemShare))
            session.execute(delete(ExpenseItem))
    with pytest.raises(expenses.ExpenseSnapshotInvalid):
        h.read(saved.id)
    with h.db.sessions() as session, pytest.raises(expenses.ExpenseSnapshotInvalid):
        with expenses.locked_edit(session, 10, saved.id) as editor:
            editor.replace_snapshot(restaurant(), allow_receipt=True)


def test_large_receipt_reads_one_snapshot_without_cartesian_rows_or_n_plus_one(
    h: Harness,
) -> None:
    members = (10, 20, 30, *range(100, 127))
    with h.db.sessions() as session, session.begin():
        session.add_all(User(id=uid, telegram_id=uid) for uid in members[3:])
        session.flush()
        session.add_all(
            GroupMember(group_id=h.group, user_id=uid, slot=n)
            for n, uid in enumerate(members[3:], 4)
        )
    first = h.create(
        ByItemsExpense(
            "Большой",
            tuple(ReceiptItemInput(str(n), "0.01", members) for n in range(50)),
        )
    )
    second = h.create(
        ByItemsExpense(
            "Другой",
            tuple(ReceiptItemInput(str(n), "0.02", members) for n in range(50)),
        )
    )
    statements: list[str] = []
    rowcounts: list[int] = []

    def capture(*args: Any) -> None:
        statements.append(args[2])
        if args[2].lstrip().upper().startswith("WITH"):
            rowcounts.append(args[1].rowcount)

    event.listen(h.db.engine, "after_cursor_execute", capture)
    try:
        assert h.read(first.id) == first
        assert len(statements) == 1 and rowcounts == [1530]
        statements.clear()
        with h.db.sessions() as session:
            values = expenses.list_expenses(session, h.group, 10, limit=2)
        assert values == [first, second] and len(statements) <= 3
        assert rowcounts[-1] == 3060
        statements.clear()
        with h.db.sessions() as session:
            assert expenses.list_expenses(session, h.group, 10, limit=1) == [first]
        assert len(statements) <= 3 and rowcounts[-1] == 1530
    finally:
        event.remove(h.db.engine, "after_cursor_execute", capture)


def test_reader_sees_whole_old_receipt_until_writer_commits(h: Harness) -> None:
    saved = h.create()
    written, release = Event(), Event()

    def write() -> ExpenseSnapshot:
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 10, saved.id) as editor,
        ):
            changed = editor.replace_snapshot(penny(), allow_receipt=True)
            written.set()
            assert release.wait(timeout=10)
        return changed

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(write)
        try:
            assert written.wait(timeout=5)
            assert h.read(saved.id) == saved
        finally:
            release.set()
        changed = future.result(timeout=5)
    assert h.read(saved.id) == changed


def overlap(h: Harness, actions: list[Callable[[], str]]) -> list[str]:
    barrier = Barrier(len(actions) + 1)

    def run(action: Callable[[], str]) -> str:
        barrier.wait(timeout=10)
        return action()

    with (
        ThreadPoolExecutor(max_workers=len(actions)) as pool,
        h.db.engine.connect() as blocker,
    ):
        transaction = blocker.begin()
        blocker.execute(select(Group).where(Group.id == h.group).with_for_update())
        futures = [pool.submit(run, action) for action in actions]
        barrier.wait(timeout=10)
        try:
            deadline = monotonic() + 2
            while True:
                with h.db.engine.connect() as observer:
                    waiting = observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock'"
                        )
                    )
                if waiting is not None and waiting >= len(actions):
                    break
                assert monotonic() < deadline, (
                    "Workers did not overlap at PostgreSQL locks"
                )
                sleep(0.01)
        finally:
            transaction.rollback()
        return [future.result(timeout=10) for future in futures]


def test_overlapping_first_insert_with_uuid_cannot_duplicate_any_level(
    h: Harness,
) -> None:
    key = uuid4()

    def create() -> str:
        try:
            h.create(key=key)
            return "created"
        except expenses.ExpenseRequestExists:
            return "occupied_internal_helper"

    assert sorted(overlap(h, [create, create])) == [
        "created",
        "occupied_internal_helper",
    ]
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
        assert session.scalar(select(func.count()).select_from(ExpenseItem)) == 4
        assert session.scalar(select(func.count()).select_from(ExpenseItemShare)) == 6


def test_overlapping_receipt_replace_delete_is_atomic_and_does_not_resurrect(
    h: Harness,
) -> None:
    saved = h.create()

    def replace() -> str:
        try:
            with (
                h.db.sessions() as session,
                expenses.locked_edit(session, 10, saved.id) as editor,
            ):
                editor.replace_snapshot(penny(), allow_receipt=True)
            return "changed"
        except expenses.ExpenseNotFound:
            return "deleted"

    def remove() -> str:
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 10, saved.id) as editor,
        ):
            editor.mark_deleted()
        return "deleted"

    assert "deleted" in overlap(h, [replace, remove])
    with (
        h.db.sessions() as session,
        expenses.locked_edit(session, 10, saved.id, include_deleted=True) as editor,
    ):
        final = editor.snapshot()
    assert final.deleted_at is not None
    assert (final.amount_kopecks, len(final.items)) in ((320000, 4), (2, 2))


def test_old_equal_post_replay_keeps_its_original_json_after_internal_receipt_replacement(
    h: Harness,
) -> None:
    payload = dict(
        title="Обед",
        split_mode="equal",
        amount="100.00",
        participants=[30, 10, 20],
        client_request_id=str(uuid4()),
    )
    headers = {
        "Authorization": "Bearer "
        + create_access_token(10, h.settings.require_jwt_secret(), 15)
    }
    with TestClient(create_app(h.settings)) as client:
        first = client.post(
            f"/groups/{h.group}/expenses", json=payload, headers=headers
        )
        assert first.status_code == 201
        original = first.json()
        eid = original["expense"]["id"]
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 10, eid) as editor,
        ):
            editor.replace_snapshot(restaurant(), allow_receipt=True)
        assert (
            client.post(
                f"/groups/{h.group}/expenses", json=payload, headers=headers
            ).json()
            == original
        )
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 10, eid) as editor,
        ):
            editor.mark_deleted()
        replay = client.post(
            f"/groups/{h.group}/expenses", json=payload, headers=headers
        )
        assert replay.status_code == 200 and replay.json() == original
        assert "items" not in replay.json()["expense"]


def test_by_items_wire_opens_after_checkpoint_approval(h: Harness) -> None:
    headers = {
        "Authorization": "Bearer "
        + create_access_token(10, h.settings.require_jwt_secret(), 15)
    }
    payload = dict(
        title="Чек",
        split_mode="by_items",
        items=[dict(title="Чай", amount="1.00", participants=[10])],
        client_request_id=str(uuid4()),
    )
    with TestClient(create_app(h.settings)) as client:
        response = client.post(
            f"/groups/{h.group}/expenses", json=payload, headers=headers
        )
        assert (
            response.status_code == 201
            and response.json()["expense"]["items"][0]["amount"] == "1.00"
        )
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
