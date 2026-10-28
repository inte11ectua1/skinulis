"""Real PostgreSQL O-04 primitives; not public CRUD/replay/stale-PUT acceptance."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Barrier, Event
from time import monotonic, sleep
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.core.errors import ApiError
from app.core.migrate import main as migrate
from app.db import Database
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
from app.services.expenses import CustomExpense, EqualExpense, ExpenseSnapshot
from app.services.money import MoneyError
from app.services.splits import SplitError

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 28, 10, tzinfo=UTC)


@dataclass
class Harness:
    db: Database
    group: int
    other_group: int

    def create(
        self,
        draft: expenses.ExpenseInput | None = None,
        *,
        actor: int = 2,
        key: UUID | None = None,
        group: int | None = None,
    ) -> ExpenseSnapshot:
        with self.db.sessions() as session:
            return expenses.create_once(
                session,
                self.group if group is None else group,
                actor,
                uuid4() if key is None else key,
                EqualExpense("Обед", "100.00", (5, 1, 2)) if draft is None else draft,
            )

    def read(self, expense_id: int, actor: int = 1) -> ExpenseSnapshot:
        with self.db.sessions() as session:
            return expenses.read_expense(session, actor, expense_id)


@pytest.fixture
def h(database_url: URL) -> Iterator[Harness]:
    assert database_url.database and database_url.database.startswith(
        "skinulis_t03_test_"
    )
    assert migrate() == 0
    database = Database(Settings(_env_file=None))
    try:
        with database.sessions() as session, session.begin():
            session.add_all(User(id=uid, telegram_id=uid) for uid in (1, 2, 5, 10, 20))
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
            result = Harness(database, group.id, other.id)
        yield result
    finally:
        database.close()


def test_create_read_exact_snapshots_and_member_without_payer_consumption(
    h: Harness,
) -> None:
    normal = h.create()
    assert normal.payer_id == 2
    assert normal.shares == ((1, 3334), (2, 3333), (5, 3333))
    assert h.read(normal.id) == normal
    penny = h.create(EqualExpense("Копейка", "0.01", (5, 2, 1)))
    assert h.read(penny.id).shares == ((1, 1), (2, 0), (5, 0))
    custom = h.create(
        CustomExpense(
            " e\u0301да ", "100.00", ((5, "60.00"), (1, "0.00"), (2, "40.00"))
        )
    )
    assert custom.title == "éда"
    assert custom.shares == ((1, 0), (2, 4000), (5, 6000))
    alone = h.create(EqualExpense("Чай", "1.00", (5,)))
    assert alone.payer_id == 2 and alone.shares == ((5, 100),)


@pytest.mark.parametrize(
    "draft",
    [
        CustomExpense("Еда", "100.00", ((1, "40.00"), (2, "59.99"))),
        CustomExpense("Еда", "100.00", ((1, "40.00"), (2, "60.01"))),
        CustomExpense("Еда", "100.00", ((1, "-0.01"), (2, "100.01"))),
        EqualExpense("Еда", "0.00", (1,)),
        EqualExpense("Еда", "1000000.01", (1,)),
        EqualExpense("Еда", "1.00", (1, 1)),
        EqualExpense("Еда", "1.00", (10,)),
        EqualExpense(" \u2003 ", "1.00", (1,)),
        EqualExpense("👩\u200d💻", "1.00", (1,)),
    ],
)
def test_invalid_draft_rolls_back_without_rows(
    h: Harness, draft: expenses.ExpenseInput
) -> None:
    with pytest.raises((SplitError, MoneyError, ValueError)):
        h.create(draft)
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 0
        assert session.scalar(select(func.count()).select_from(ExpenseShare)) == 0


def test_foreign_group_and_expense_are_hidden_author_rules_include_owner(
    h: Harness,
) -> None:
    saved = h.create()
    for group in (h.other_group, 2**62):
        with pytest.raises(ApiError) as error:
            h.create(actor=2, group=group)
        assert (error.value.status, error.value.code) == (404, "group_not_found")
    for expense_id in (saved.id, 2**62):
        with pytest.raises(expenses.ExpenseNotFound, match="^Expense not found$"):
            h.read(expense_id, actor=10)
        with (
            h.db.sessions() as session,
            pytest.raises(expenses.ExpenseNotFound, match="^Expense not found$"),
        ):
            with expenses.locked_edit(session, 10, expense_id):
                pytest.fail("Foreign actor obtained an editor")
    for actor in (1, 5):
        with h.db.sessions() as session, pytest.raises(expenses.ExpenseAuthorRequired):
            with expenses.locked_edit(session, actor, saved.id) as editor:
                editor.mark_deleted()
    assert h.read(saved.id) == saved


def test_author_replaces_whole_snapshot_and_keeps_identity(h: Harness) -> None:
    before = h.create()
    with h.db.sessions() as session:
        # Auth's normal autobegin and a preloaded old snapshot share this Session.
        session.get(User, 2)
        session.scalars(
            select(ExpenseShare).where(ExpenseShare.expense_id == before.id)
        ).all()
        with expenses.locked_edit(session, 2, before.id) as editor:
            current = editor.snapshot()
            assert current == before
            after = editor.replace_snapshot(
                CustomExpense(" Чай ", "1.00", ((5, "1.00"), (1, "0.00")))
            )
    assert after.title == "Чай" and after.split_mode == "custom"
    assert after.shares == ((1, 0), (5, 100))
    assert (
        after.id,
        after.group_id,
        after.payer_id,
        after.client_request_id,
        after.created_at,
    ) == (
        before.id,
        before.group_id,
        before.payer_id,
        before.client_request_id,
        before.created_at,
    )
    assert h.read(before.id) == after
    with pytest.raises(RuntimeError):
        editor.mark_deleted()


def test_failure_after_deleting_old_shares_rolls_back_entire_replacement(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = h.create()
    with h.db.sessions() as session:
        original_flush = session.flush

        def fail_on_new_share(objects: Any = None) -> None:
            if any(isinstance(value, ExpenseShare) for value in session.new):
                # Flush one invalid row after the expense UPDATE and bulk DELETE.
                invalid = next(
                    value for value in session.new if isinstance(value, ExpenseShare)
                )
                invalid.amount_kopecks = -1
            original_flush(objects)

        monkeypatch.setattr(session, "flush", fail_on_new_share)
        with pytest.raises(IntegrityError):
            with expenses.locked_edit(session, 2, before.id) as editor:
                editor.replace_snapshot(EqualExpense("Changed", "2.00", (5,)))
        assert not session.in_transaction()
    assert h.read(before.id) == before


def test_soft_delete_repeat_preserves_snapshots_and_confirmed_settlements(
    h: Harness,
) -> None:
    saved = h.create()
    with h.db.sessions() as session, session.begin():
        settlement = Settlement(
            group_id=h.group,
            sender_id=5,
            receiver_id=2,
            amount_kopecks=100,
            status="confirmed",
            client_request_id=uuid4(),
            created_at=NOW,
            resolved_at=NOW,
        )
        session.add(settlement)
        session.flush()
        settlement_id = settlement.id
    with h.db.sessions() as session:
        with expenses.locked_edit(session, 2, saved.id) as editor:
            editor.replace_snapshot(EqualExpense("Changed", "2.00", (1,)))
        with expenses.locked_edit(session, 2, saved.id) as editor:
            deleted = editor.mark_deleted()
        with expenses.locked_edit(session, 2, saved.id, include_deleted=True) as editor:
            assert editor.mark_deleted() == deleted
        with pytest.raises(expenses.ExpenseNotFound):
            with expenses.locked_edit(session, 2, saved.id) as editor:
                editor.replace_snapshot(EqualExpense("No resurrection", "1.00", (5,)))
    with pytest.raises(expenses.ExpenseNotFound):
        h.read(saved.id)
    with h.db.sessions() as session:
        assert expenses.list_expenses(session, h.group, 1) == []
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
        assert list(
            session.execute(select(ExpenseShare.user_id, ExpenseShare.amount_kopecks))
        ) == [(1, 200)]
        stored_settlement = session.get(Settlement, settlement_id)
        assert stored_settlement is not None
        assert (
            stored_settlement.status,
            stored_settlement.amount_kopecks,
            stored_settlement.resolved_at,
        ) == ("confirmed", 100, NOW)


def test_occupied_uuid_is_a_policy_blocker_even_after_edit_or_delete(
    h: Harness,
) -> None:
    key = uuid4()
    before = h.create(key=key)
    for actor in (2, 1):
        with pytest.raises(expenses.ExpenseRequestExists):
            h.create(actor=actor, key=key)
    with h.db.sessions() as session:
        with expenses.locked_edit(session, 2, before.id) as editor:
            editor.replace_snapshot(EqualExpense("New", "2.00", (1,)))
        with expenses.locked_edit(session, 2, before.id) as editor:
            editor.mark_deleted()
    with pytest.raises(expenses.ExpenseRequestExists):
        h.create(key=key)
    assert (
        h.create(
            EqualExpense("Other", "1.00", (10,)), actor=10, group=h.other_group, key=key
        ).group_id
        == h.other_group
    )


def test_new_member_never_rewrites_saved_shares(h: Harness) -> None:
    saved = h.create()
    with h.db.sessions() as session, session.begin():
        session.add(GroupMember(group_id=h.group, user_id=20, slot=4))
    assert h.read(saved.id, actor=20) == saved


def test_list_paginates_expenses_before_joining_shares_without_n_plus_one(
    h: Harness,
) -> None:
    saved = [h.create() for _ in range(23)]
    with h.db.sessions() as session, session.begin():
        session.execute(update(Expense).values(created_at=NOW))
    queries: list[str] = []

    def capture(*args: Any) -> None:
        queries.append(args[2])

    event.listen(h.db.engine, "before_cursor_execute", capture)
    try:
        with h.db.sessions() as session:
            first = expenses.list_expenses(session, h.group, 1)
        first_query_count = len(queries)
        queries.clear()
        with h.db.sessions() as session:
            last = expenses.list_expenses(session, h.group, 1, limit=20, offset=20)
        assert len(queries) == first_query_count <= 3
        assert [value.id for value in first] == [value.id for value in saved[:20]]
        assert [value.id for value in last] == [value.id for value in saved[20:]]
        assert all(len(value.shares) == 3 for value in [*first, *last])
        queries.clear()
        h.read(saved[0].id)
        assert len(queries) == 1  # Metadata + shares from one SQL snapshot.
    finally:
        event.remove(h.db.engine, "before_cursor_execute", capture)
    with h.db.sessions() as session:
        assert expenses.list_expenses(session, h.group, 1, offset=100) == []


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
                    "Workers did not overlap at a PostgreSQL lock"
                )
                sleep(0.01)
        finally:
            transaction.rollback()
        return [future.result(timeout=10) for future in futures]


@pytest.mark.parametrize("different_body", [False, True])
def test_concurrent_first_inserts_cannot_duplicate_uuid(
    h: Harness, different_body: bool
) -> None:
    key = uuid4()

    def action(amount: str) -> Callable[[], str]:
        def run() -> str:
            try:
                h.create(EqualExpense("Concurrent", amount, (1, 5)), key=key)
                return "created"
            except expenses.ExpenseRequestExists:
                return "occupied_contract_pending"

        return run

    results = overlap(h, [action("1.00"), action("2.00" if different_body else "1.00")])
    assert sorted(results) == ["created", "occupied_contract_pending"]
    with h.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
        expense = session.scalar(select(Expense))
        assert expense is not None
        assert (
            session.scalar(select(func.sum(ExpenseShare.amount_kopecks)))
            == expense.amount_kopecks
        )


def test_overlapping_replacement_primitives_are_atomic_without_claiming_stale_policy(
    h: Harness,
) -> None:
    saved = h.create()

    def action(amount: str, user_id: int) -> Callable[[], str]:
        def run() -> str:
            with (
                h.db.sessions() as session,
                expenses.locked_edit(session, 2, saved.id) as editor,
            ):
                editor.replace_snapshot(EqualExpense("Concurrent", amount, (user_id,)))
            return "replaced"

        return run

    assert overlap(h, [action("1.00", 1), action("2.00", 5)]) == [
        "replaced",
        "replaced",
    ]
    after = h.read(saved.id)
    assert (after.amount_kopecks, after.shares) in [
        (100, ((1, 100),)),
        (200, ((5, 200),)),
    ]


def test_overlapping_replace_and_delete_never_resurrect_or_leave_partial_shares(
    h: Harness,
) -> None:
    saved = h.create()

    def replace() -> str:
        try:
            with (
                h.db.sessions() as session,
                expenses.locked_edit(session, 2, saved.id) as editor,
            ):
                editor.replace_snapshot(EqualExpense("Concurrent", "1.00", (5,)))
            return "replaced"
        except expenses.ExpenseNotFound:
            return "deleted"

    def remove() -> str:
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 2, saved.id) as editor,
        ):
            editor.mark_deleted()
        return "deleted"

    assert "deleted" in overlap(h, [replace, remove])
    with h.db.sessions() as session:
        expense = session.get(Expense, saved.id)
        assert expense is not None and expense.deleted_at is not None
        assert (
            session.scalar(select(func.sum(ExpenseShare.amount_kopecks)))
            == expense.amount_kopecks
        )


def test_other_group_write_does_not_wait_for_locked_group(h: Harness) -> None:
    with h.db.engine.connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(select(Group).where(Group.id == h.group).with_for_update())
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(
                    lambda: h.create(
                        EqualExpense("Other", "1.00", (10,)),
                        actor=10,
                        group=h.other_group,
                    )
                ).result(timeout=2)
            assert result.group_id == h.other_group
        finally:
            transaction.rollback()


def test_group_lock_is_first_row_lock_for_create_and_replacement(h: Harness) -> None:
    statements: list[str] = []

    def capture(*args: Any) -> None:
        statements.append(args[2])

    event.listen(h.db.engine, "before_cursor_execute", capture)
    try:
        saved = h.create()
        locks = [sql.lower() for sql in statements if "FOR UPDATE" in sql]
        assert len(locks) == 1 and "from groups" in locks[0]
        statements.clear()
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 2, saved.id) as editor,
        ):
            editor.replace_snapshot(EqualExpense("Changed", "1.00", (5,)))
        locks = [sql.lower() for sql in statements if "FOR UPDATE" in sql]
        assert (
            len(locks) == 2
            and "from groups" in locks[0]
            and "from expenses" in locks[1]
        )
    finally:
        event.remove(h.db.engine, "before_cursor_execute", capture)


def test_editor_cannot_write_after_early_manual_commit(h: Harness) -> None:
    saved = h.create()
    with (
        h.db.sessions() as session,
        expenses.locked_edit(session, 2, saved.id) as editor,
    ):
        session.commit()
        with pytest.raises(RuntimeError):
            editor.mark_deleted()
    assert h.read(saved.id) == saved


def test_nested_receipt_is_preserved_and_not_replaced_by_o04(h: Harness) -> None:
    saved = h.create(EqualExpense("Чек", "1.00", (5,)))
    with h.db.sessions() as session, session.begin():
        expense = session.get(Expense, saved.id)
        assert expense is not None
        expense.split_mode = "by_items"
        item = ExpenseItem(
            expense_id=saved.id,
            group_id=h.group,
            title="Чай",
            amount_kopecks=100,
            position=1,
        )
        session.add(item)
        session.flush()
        item_id = item.id
        session.add(
            ExpenseItemShare(
                item_id=item_id,
                expense_id=saved.id,
                group_id=h.group,
                user_id=5,
                amount_kopecks=100,
            )
        )
    with h.db.sessions() as session:
        with pytest.raises(expenses.ExpenseDetailsUnsupported):
            with expenses.locked_edit(session, 2, saved.id) as editor:
                editor.replace_snapshot(EqualExpense("No", "1.00", (1,)))
        with expenses.locked_edit(session, 2, saved.id) as editor:
            editor.mark_deleted()
    with h.db.sessions() as session:
        assert session.get(ExpenseItem, item_id) is not None
        assert session.get(ExpenseItemShare, (item_id, 5)) is not None
        assert session.get(ExpenseShare, (saved.id, 5)) is not None


def test_reader_sees_a_complete_snapshot_while_writer_has_uncommitted_replacement(
    h: Harness,
) -> None:
    saved = h.create()
    written, release = Event(), Event()

    def writer() -> ExpenseSnapshot:
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 2, saved.id) as editor,
        ):
            result = editor.replace_snapshot(EqualExpense("New", "2.00", (5,)))
            written.set()
            assert release.wait(timeout=10)
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        try:
            assert written.wait(timeout=5)
            assert h.read(saved.id) == saved  # Reads do not wait for group row locks.
        finally:
            release.set()
        after = future.result(timeout=5)
    assert h.read(saved.id) == after


def test_preloaded_expense_is_refreshed_under_lock(h: Harness) -> None:
    saved = h.create()
    with h.db.sessions() as stale_session:
        old = stale_session.get(Expense, saved.id)
        assert old is not None
        with (
            h.db.sessions() as other,
            expenses.locked_edit(other, 2, saved.id) as editor,
        ):
            changed = editor.replace_snapshot(EqualExpense("New", "2.00", (5,)))
        assert old.amount_kopecks == saved.amount_kopecks
        with expenses.locked_edit(stale_session, 2, saved.id) as editor:
            assert editor.snapshot() == changed


@pytest.mark.parametrize("bad_id", [True, 1.0, "2", 0, 2**63])
def test_internal_actor_ids_are_strict_before_membership_lookup(
    h: Harness, bad_id: Any
) -> None:
    with pytest.raises(ValueError, match="Identifier"):
        h.create(actor=bad_id)


@pytest.mark.parametrize("missing", [False, True])
def test_invalid_stored_snapshot_is_not_returned_as_valid_or_repaired(
    h: Harness, missing: bool
) -> None:
    saved = h.create()
    with h.db.sessions() as session, session.begin():
        if missing:
            session.execute(
                text("DELETE FROM expense_shares WHERE expense_id=:id"),
                {"id": saved.id},
            )
        else:
            session.execute(
                update(ExpenseShare)
                .where(ExpenseShare.expense_id == saved.id)
                .values(amount_kopecks=0)
            )
    with pytest.raises(expenses.ExpenseSnapshotInvalid):
        h.read(saved.id)
    with h.db.sessions() as session, pytest.raises(expenses.ExpenseSnapshotInvalid):
        expenses.list_expenses(session, h.group, 1)
    with h.db.sessions() as session:
        assert (
            session.scalar(
                select(func.coalesce(func.sum(ExpenseShare.amount_kopecks), 0))
            )
            == 0
        )


def test_overlapping_delete_primitives_keep_the_same_tombstone(h: Harness) -> None:
    saved = h.create()

    def remove() -> str:
        with (
            h.db.sessions() as session,
            expenses.locked_edit(session, 2, saved.id, include_deleted=True) as editor,
        ):
            deleted_at = editor.mark_deleted().deleted_at
            assert deleted_at is not None
            return deleted_at.isoformat()

    results = overlap(h, [remove, remove])
    assert len(set(results)) == 1
