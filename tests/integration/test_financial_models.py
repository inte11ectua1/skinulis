"""Storage guarantees on disposable PostgreSQL 17; no financial API is exercised."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import Error as PostgreSQLError
from sqlalchemy import (
    BigInteger,
    DateTime,
    create_engine,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.core.migrate import main as migrate
from app.models import (
    Base,
    Expense,
    ExpenseItem,
    ExpenseItemShare,
    ExpenseShare,
    Group,
    GroupMember,
    Settlement,
    User,
)

pytestmark = pytest.mark.integration
TABLES = (
    "expenses",
    "expense_items",
    "expense_shares",
    "expense_item_shares",
    "settlements",
)
NOW = datetime(2026, 10, 28, 9, tzinfo=UTC)


@dataclass(frozen=True)
class FinanceDB:
    engine: Engine
    group: int
    other_group: int
    owner: int
    member: int
    outsider: int
    newcomer: int
    expense: int
    other_expense: int
    item: int
    settlement: int

    def values(self, table: str) -> dict[str, Any]:
        """Fresh valid insert; tests override precisely the field under examination."""
        match table:
            case "expenses":
                return dict(
                    group_id=self.group,
                    payer_id=self.owner,
                    title="Еда",
                    split_mode="custom",
                    amount_kopecks=100,
                    client_request_id=uuid4(),
                )
            case "expense_items":
                return dict(
                    expense_id=self.expense,
                    group_id=self.group,
                    title="Чай",
                    amount_kopecks=100,
                    position=2,
                )
            case "expense_shares":
                return dict(
                    expense_id=self.other_expense,
                    group_id=self.other_group,
                    user_id=self.member,
                    amount_kopecks=100,
                )
            case "expense_item_shares":
                return dict(
                    item_id=self.item,
                    expense_id=self.expense,
                    group_id=self.group,
                    user_id=self.owner,
                    amount_kopecks=0,
                )
            case "settlements":
                return dict(
                    group_id=self.group,
                    sender_id=self.member,
                    receiver_id=self.owner,
                    amount_kopecks=150000000,
                    client_request_id=uuid4(),
                )
            case _:
                raise AssertionError(table)


def seed_identity(engine: Engine) -> tuple[int, int, int, int, int, int]:
    """Existing identity contracts, including the deferred owner membership FK."""
    owner, member, outsider, newcomer = (2**40 + n for n in range(1, 5))
    with Session(engine) as session, session.begin():
        session.add_all(
            User(id=uid, telegram_id=uid) for uid in (owner, member, outsider, newcomer)
        )
        session.flush()
        first = Group(owner_id=owner, name="Поездка", client_request_id=uuid4())
        second = Group(owner_id=owner, name="Другая", client_request_id=uuid4())
        session.add_all([first, second])
        session.flush()
        session.add_all(
            [
                GroupMember(group_id=first.id, user_id=owner, slot=1),
                GroupMember(group_id=first.id, user_id=member, slot=2),
                GroupMember(group_id=second.id, user_id=owner, slot=1),
                GroupMember(group_id=second.id, user_id=member, slot=2),
                GroupMember(group_id=second.id, user_id=outsider, slot=3),
            ]
        )
        return first.id, second.id, owner, member, outsider, newcomer


@pytest.fixture
def finance(database_url: URL) -> Iterator[FinanceDB]:
    assert migrate() == 0
    engine = create_engine(database_url, hide_parameters=True)
    try:
        group, other_group, owner, member, outsider, newcomer = seed_identity(engine)
        with Session(engine) as session, session.begin():
            expense = Expense(
                group_id=group,
                payer_id=owner,
                title="Чек",
                split_mode="by_items",
                amount_kopecks=100,
                client_request_id=uuid4(),
                created_at=NOW,
            )
            other = Expense(
                group_id=other_group,
                payer_id=owner,
                title="Второй",
                split_mode="equal",
                amount_kopecks=100,
                client_request_id=uuid4(),
            )
            session.add_all([expense, other])
            session.flush()
            item = ExpenseItem(
                expense_id=expense.id,
                group_id=group,
                title="Обед",
                amount_kopecks=100,
                position=1,
            )
            session.add(item)
            session.add_all(
                [
                    ExpenseShare(
                        expense_id=expense.id,
                        user_id=owner,
                        group_id=group,
                        amount_kopecks=0,
                    ),
                    ExpenseShare(
                        expense_id=expense.id,
                        user_id=member,
                        group_id=group,
                        amount_kopecks=100,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    ExpenseItemShare(
                        item_id=item.id,
                        expense_id=expense.id,
                        user_id=owner,
                        group_id=group,
                        amount_kopecks=0,
                    ),
                    ExpenseItemShare(
                        item_id=item.id,
                        expense_id=expense.id,
                        user_id=member,
                        group_id=group,
                        amount_kopecks=100,
                    ),
                ]
            )
            settlement = Settlement(
                group_id=group,
                sender_id=member,
                receiver_id=owner,
                amount_kopecks=150000000,
                status="confirmed",
                client_request_id=uuid4(),
                created_at=NOW,
                resolved_at=NOW,
            )
            session.add(settlement)
            session.flush()
            result = FinanceDB(
                engine,
                group,
                other_group,
                owner,
                member,
                outsider,
                newcomer,
                expense.id,
                other.id,
                item.id,
                settlement.id,
            )
        yield result
    finally:
        engine.dispose()


def rejected_insert(
    finance: FinanceDB,
    table: str,
    overrides: dict[str, Any],
    constraint: str | tuple[str, ...],
) -> None:
    values = finance.values(table) | overrides
    with pytest.raises(IntegrityError) as error, finance.engine.begin() as connection:
        connection.execute(Base.metadata.tables[table].insert().values(**values))
    expected = (constraint,) if isinstance(constraint, str) else constraint
    assert isinstance(error.value.orig, PostgreSQLError)
    assert error.value.orig.diag.constraint_name in expected


def test_upgrade_preserves_identity_and_downgrade_only_removes_finance(
    database_url: URL,
) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "0003_groups_identity")
    engine = create_engine(database_url, hide_parameters=True)
    try:
        identity = seed_identity(engine)
        with engine.connect() as connection:
            before = {
                table: connection.execute(
                    text(f"SELECT * FROM {table} ORDER BY 1, 2")
                ).all()
                for table in ("users", "groups", "group_members")
            }
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert ScriptDirectory.from_config(config).get_heads() == [
            "0004_financial_domain"
        ]
        command.check(config)
        with engine.connect() as connection:
            for table, rows in before.items():
                assert (
                    connection.execute(
                        text(f"SELECT * FROM {table} ORDER BY 1, 2")
                    ).all()
                    == rows
                )
        command.downgrade(config, "0003_groups_identity")
        assert not set(TABLES).intersection(inspect(engine).get_table_names())
        with Session(engine) as session:
            assert session.get(GroupMember, (identity[0], identity[2])) is not None
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("table", "amount", "constraint"),
    [
        ("expenses", 0, "ck_expenses_amount"),
        ("expenses", -1, "ck_expenses_amount"),
        ("expenses", 100000001, "ck_expenses_amount"),
        ("expense_items", 0, "ck_expense_items_amount"),
        ("expense_items", -1, "ck_expense_items_amount"),
        ("expense_shares", -1, "ck_expense_shares_amount"),
        ("expense_item_shares", -1, "ck_expense_item_shares_amount"),
        ("settlements", 0, "ck_settlements_amount"),
        ("settlements", -1, "ck_settlements_amount"),
    ],
)
def test_invalid_amounts(
    finance: FinanceDB, table: str, amount: int, constraint: str
) -> None:
    if table == "expense_item_shares":
        with finance.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM expense_item_shares WHERE user_id=:uid"),
                {"uid": finance.owner},
            )
    rejected_insert(finance, table, {"amount_kopecks": amount}, constraint)


@pytest.mark.parametrize(
    ("table", "field", "value", "constraint"),
    [
        ("expenses", "split_mode", "invalid", "ck_expenses_split_mode"),
        ("expenses", "title", "", "ck_expenses_title"),
        ("expense_items", "title", "", "ck_expense_items_title"),
        ("expense_items", "position", 0, "ck_expense_items_position"),
        ("expense_items", "position", 51, "ck_expense_items_position"),
        ("expense_items", "position", 1, "uq_expense_items_position"),
        (
            "settlements",
            "status",
            "invalid",
            ("ck_settlements_status", "ck_settlements_resolved_at"),
        ),
        ("expenses", "id", 0, "ck_expenses_id_positive"),
        ("expense_items", "id", -1, "ck_expense_items_id_positive"),
        ("settlements", "id", 0, "ck_settlements_id_positive"),
    ],
)
def test_checks(
    finance: FinanceDB,
    table: str,
    field: str,
    value: Any,
    constraint: str | tuple[str, ...],
) -> None:
    rejected_insert(finance, table, {field: value}, constraint)


@pytest.mark.parametrize(
    ("table", "field", "identity", "constraint"),
    [
        (
            "expenses",
            "group_id",
            "missing",
            ("fk_expenses_group", "fk_expenses_payer_membership"),
        ),
        ("expenses", "payer_id", "missing", "fk_expenses_payer_membership"),
        ("expenses", "payer_id", "outsider", "fk_expenses_payer_membership"),
        ("expense_items", "expense_id", "missing", "fk_expense_items_expense"),
        ("expense_items", "group_id", "other_group", "fk_expense_items_expense"),
        ("expense_shares", "user_id", "missing", "fk_expense_shares_membership"),
        ("expense_shares", "group_id", "group", "fk_expense_shares_expense"),
        (
            "settlements",
            "group_id",
            "missing",
            (
                "fk_settlements_group",
                "fk_settlements_sender_membership",
                "fk_settlements_receiver_membership",
            ),
        ),
        ("settlements", "sender_id", "outsider", "fk_settlements_sender_membership"),
        (
            "settlements",
            "receiver_id",
            "outsider",
            "fk_settlements_receiver_membership",
        ),
        ("settlements", "sender_id", "missing", "fk_settlements_sender_membership"),
        ("settlements", "receiver_id", "missing", "fk_settlements_receiver_membership"),
    ],
)
def test_parent_and_membership_fks(
    finance: FinanceDB,
    table: str,
    field: str,
    identity: str,
    constraint: str | tuple[str, ...],
) -> None:
    value = 2**62 if identity == "missing" else getattr(finance, identity)
    rejected_insert(finance, table, {field: value}, constraint)


def test_final_and_item_shares_cannot_cross_groups_or_expenses(
    finance: FinanceDB,
) -> None:
    rejected_insert(
        finance,
        "expense_shares",
        dict(
            expense_id=finance.expense, group_id=finance.group, user_id=finance.outsider
        ),
        "fk_expense_shares_membership",
    )
    with finance.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM expense_item_shares WHERE user_id=:uid"),
            {"uid": finance.owner},
        )
    cases: list[tuple[dict[str, Any], str | tuple[str, ...]]] = [
        ({"group_id": finance.other_group}, "fk_expense_item_shares_item"),
        ({"item_id": 2**62}, "fk_expense_item_shares_item"),
        (
            {"expense_id": finance.other_expense},
            ("fk_expense_item_shares_final_share", "fk_expense_item_shares_item"),
        ),
        ({"user_id": finance.outsider}, "fk_expense_item_shares_final_share"),
        ({"user_id": 2**62}, "fk_expense_item_shares_final_share"),
    ]
    for overrides, constraint in cases:
        rejected_insert(finance, "expense_item_shares", overrides, constraint)
    # Both users belong to both groups: existence alone cannot permit a wrong parent.
    with finance.engine.begin() as connection:
        connection.execute(
            insert(ExpenseShare).values(
                **(finance.values("expense_shares") | {"user_id": finance.owner})
            )
        )
    rejected_insert(
        finance,
        "expense_item_shares",
        {
            "expense_id": finance.other_expense,
            "group_id": finance.other_group,
            "user_id": finance.owner,
        },
        "fk_expense_item_shares_item",
    )


def test_unique_requests_are_scoped_by_group_and_operation(finance: FinanceDB) -> None:
    key = uuid4()
    for table in ("expenses", "settlements"):
        values = finance.values(table) | {"client_request_id": key}
        with finance.engine.begin() as connection:
            connection.execute(Base.metadata.tables[table].insert().values(**values))
            connection.execute(
                Base.metadata.tables[table]
                .insert()
                .values(**(values | {"group_id": finance.other_group}))
            )
        rejected_insert(
            finance, table, {"client_request_id": key}, f"uq_{table}_request"
        )
    with finance.engine.begin() as connection:
        connection.execute(
            update(Expense)
            .where(Expense.client_request_id == key, Expense.group_id == finance.group)
            .values(deleted_at=Expense.created_at)
        )
    rejected_insert(
        finance, "expenses", {"client_request_id": key}, "uq_expenses_request"
    )


def test_duplicate_shares_rejected(finance: FinanceDB) -> None:
    rejected_insert(
        finance,
        "expense_shares",
        {"expense_id": finance.expense, "group_id": finance.group},
        "pk_expense_shares",
    )
    rejected_insert(finance, "expense_item_shares", {}, "pk_expense_item_shares")


@pytest.mark.parametrize("status", ["confirmed", "rejected", "cancelled"])
def test_terminal_time_structure(finance: FinanceDB, status: str) -> None:
    rejected_insert(
        finance, "settlements", {"status": status}, "ck_settlements_resolved_at"
    )
    rejected_insert(
        finance,
        "settlements",
        {
            "status": status,
            "created_at": NOW,
            "resolved_at": NOW - timedelta(seconds=1),
        },
        "ck_settlements_resolved_at",
    )
    with finance.engine.begin() as connection:
        connection.execute(
            insert(Settlement).values(
                **(
                    finance.values("settlements")
                    | {"status": status, "created_at": NOW, "resolved_at": NOW}
                )
            )
        )


def test_pending_time_distinct_parties_and_deleted_time(finance: FinanceDB) -> None:
    rejected_insert(
        finance, "settlements", {"resolved_at": NOW}, "ck_settlements_resolved_at"
    )
    rejected_insert(
        finance, "settlements", {"sender_id": finance.owner}, "ck_settlements_parties"
    )
    rejected_insert(
        finance,
        "expenses",
        {"created_at": NOW, "deleted_at": NOW - timedelta(seconds=1)},
        "ck_expenses_deleted_at",
    )


def test_zero_snapshots_new_member_and_soft_delete_preserve_history(
    finance: FinanceDB,
) -> None:
    with Session(finance.engine) as session, session.begin():
        final_zero = session.get(ExpenseShare, (finance.expense, finance.owner))
        item_zero = session.get(ExpenseItemShare, (finance.item, finance.owner))
        assert final_zero is not None and final_zero.amount_kopecks == 0
        assert item_zero is not None and item_zero.amount_kopecks == 0
        session.add(
            GroupMember(group_id=finance.group, user_id=finance.newcomer, slot=3)
        )
    with finance.engine.begin() as connection:
        connection.execute(
            text("UPDATE expenses SET deleted_at=:now WHERE id=:id"),
            {"now": NOW, "id": finance.expense},
        )
    with Session(finance.engine) as session:
        saved_expense = session.get(Expense, finance.expense)
        assert saved_expense is not None and saved_expense.deleted_at == NOW
        assert session.get(ExpenseItem, finance.item) is not None
        saved_share = session.get(ExpenseShare, (finance.expense, finance.member))
        assert saved_share is not None and saved_share.amount_kopecks == 100
        assert session.get(ExpenseItemShare, (finance.item, finance.member)) is not None
        assert session.get(ExpenseShare, (finance.expense, finance.newcomer)) is None
        saved = session.get(Settlement, finance.settlement)
        assert saved is not None
        assert (saved.status, saved.amount_kopecks, saved.resolved_at) == (
            "confirmed",
            150000000,
            NOW,
        )


@pytest.mark.parametrize(
    ("table", "predicate"),
    [
        ("users", "id=:member"),
        ("groups", "id=:group"),
        ("group_members", "group_id=:group AND user_id=:member"),
        ("expenses", "id=:expense"),
        ("expense_items", "id=:item"),
        ("expense_shares", "expense_id=:expense AND user_id=:member"),
    ],
)
def test_parent_deletion_is_restricted(
    finance: FinanceDB, table: str, predicate: str
) -> None:
    with pytest.raises(IntegrityError), finance.engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM {table} WHERE {predicate}"),
            {
                "member": finance.member,
                "group": finance.group,
                "expense": finance.expense,
                "item": finance.item,
            },
        )
    with Session(finance.engine) as session:
        assert session.get(Settlement, finance.settlement) is not None
        assert session.get(ExpenseItemShare, (finance.item, finance.member)) is not None


def test_mid_transaction_failure_rolls_back_entire_financial_write(
    finance: FinanceDB,
) -> None:
    key = uuid4()
    with (
        pytest.raises(IntegrityError),
        Session(finance.engine) as session,
        session.begin(),
    ):
        expense = Expense(**(finance.values("expenses") | {"client_request_id": key}))
        session.add(expense)
        session.flush()
        session.add(
            ExpenseItem(
                expense_id=expense.id,
                group_id=finance.group,
                title="Обед",
                amount_kopecks=100,
                position=1,
            )
        )
        session.add(
            ExpenseShare(
                expense_id=expense.id,
                group_id=finance.group,
                user_id=finance.member,
                amount_kopecks=-1,
            )
        )
        session.flush()
    with Session(finance.engine) as session:
        assert (
            session.scalar(select(Expense).where(Expense.client_request_id == key))
            is None
        )
        assert (
            session.scalar(
                select(ExpenseItem).where(ExpenseItem.expense_id == expense.id)
            )
            is None
        )
        assert (
            session.scalar(
                select(ExpenseShare).where(ExpenseShare.expense_id == expense.id)
            )
            is None
        )
    # A second transaction can use the rolled back UUID and store a complete snapshot.
    with Session(finance.engine) as session, session.begin():
        expense = Expense(**(finance.values("expenses") | {"client_request_id": key}))
        session.add(expense)
        session.flush()
        session.add(
            ExpenseShare(
                expense_id=expense.id,
                group_id=finance.group,
                user_id=finance.member,
                amount_kopecks=100,
            )
        )


def test_bigint_bounds_and_numeric_aggregation(finance: FinanceDB) -> None:
    maximum = 2**63 - 1
    with finance.engine.begin() as connection:
        for _ in range(2):
            connection.execute(
                insert(Settlement).values(
                    **(finance.values("settlements") | {"amount_kopecks": maximum})
                )
            )
        total, sql_type = connection.execute(
            text(
                "SELECT sum(amount_kopecks), pg_typeof(sum(amount_kopecks))::text FROM settlements"
            )
        ).one()
        assert isinstance(total, Decimal)
        assert int(total) == maximum * 2 + 150000000
        assert sql_type == "numeric"
    with pytest.raises(DataError), finance.engine.begin() as connection:
        connection.execute(
            insert(Settlement).values(
                **(finance.values("settlements") | {"amount_kopecks": maximum + 1})
            )
        )


@pytest.mark.parametrize("table", ["expenses", "expense_items"])
def test_raw_unicode_title_storage_proposal(finance: FinanceDB, table: str) -> None:
    for title in ("я" * 120, "e\u0301" * 60, "🍵" * 120, " Еда ", " "):
        with finance.engine.begin() as connection:
            values = finance.values(table) | {"title": title}
            statement = (
                Base.metadata.tables[table]
                .insert()
                .values(**values)
                .returning(Base.metadata.tables[table].c.title)
            )
            assert connection.execute(statement).scalar_one() == title
            # Reuse position=2 in the next independent insertion.
            if table == "expense_items":
                connection.execute(
                    text(
                        "DELETE FROM expense_items WHERE expense_id=:id AND position=2"
                    ),
                    {"id": finance.expense},
                )
    with pytest.raises(DataError), finance.engine.begin() as connection:
        connection.execute(
            Base.metadata.tables[table]
            .insert()
            .values(**(finance.values(table) | {"title": "я" * 121}))
        )


def test_fifty_item_positions_are_structurally_bounded(finance: FinanceDB) -> None:
    with finance.engine.begin() as connection:
        connection.execute(
            insert(ExpenseItem),
            [finance.values("expense_items") | {"position": n} for n in range(2, 51)],
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM expense_items WHERE expense_id=:id"),
                {"id": finance.expense},
            ).scalar_one()
            == 50
        )
    rejected_insert(
        finance, "expense_items", {"position": 51}, "ck_expense_items_position"
    )


def test_database_does_not_claim_cross_row_business_guarantees(
    finance: FinanceDB,
) -> None:
    # Deliberately inconsistent snapshots are physically possible: O-04/O-05 must
    # validate sums/mode/completeness while holding the group lock, in one transaction.
    with finance.engine.begin() as connection:
        connection.execute(
            update(Expense)
            .where(Expense.id == finance.expense)
            .values(split_mode="equal", amount_kopecks=1)
        )
        connection.execute(
            update(ExpenseShare)
            .where(ExpenseShare.expense_id == finance.expense)
            .values(amount_kopecks=999)
        )


def test_metadata_types_constraints_and_timestamp_semantics(finance: FinanceDB) -> None:
    command.check(Config("alembic.ini"))
    schema = inspect(finance.engine)
    for name in TABLES:
        table = Base.metadata.tables[name]
        assert all(constraint.name for constraint in table.constraints)
        reflected_names = {
            constraint["name"]
            for constraint in [
                schema.get_pk_constraint(name),
                *schema.get_foreign_keys(name),
                *schema.get_unique_constraints(name),
                *schema.get_check_constraints(name),
            ]
        }
        assert reflected_names == {constraint.name for constraint in table.constraints}
        assert all(
            isinstance(table.c[column].type, BigInteger)
            for column in table.c.keys()
            if column.endswith("_id")
            and column != "client_request_id"
            or column in ("id", "amount_kopecks")
        )
        assert all(fk.ondelete == "RESTRICT" for fk in table.foreign_key_constraints)
        assert all(
            fk["options"].get("ondelete") == "RESTRICT"
            for fk in schema.get_foreign_keys(name)
        )
        for column in schema.get_columns(name):
            if column["name"].endswith("_at"):
                assert isinstance(column["type"], DateTime)
                assert column["type"].timezone
    with finance.engine.begin() as connection:
        connection.execute(text("SET LOCAL TIME ZONE 'Asia/Kolkata'"))
        created, deleted = connection.execute(
            text("SELECT created_at, deleted_at FROM expenses WHERE id=:id"),
            {"id": finance.expense},
        ).one()
        assert created.utcoffset() == timedelta(hours=5, minutes=30)
        assert created.astimezone(UTC) == NOW
        assert deleted is None
        pending = connection.execute(
            insert(Settlement)
            .values(**finance.values("settlements"))
            .returning(Settlement.created_at, Settlement.status, Settlement.resolved_at)
        ).one()
        assert pending.created_at.tzinfo is not None
        assert (
            pending.created_at == connection.execute(text("SELECT now()")).scalar_one()
        )
        assert (pending.status, pending.resolved_at) == ("pending", None)


@pytest.mark.parametrize("amount", [1, 100000000])
def test_expense_amount_inclusive_bounds(finance: FinanceDB, amount: int) -> None:
    with finance.engine.begin() as connection:
        saved = connection.execute(
            insert(Expense)
            .values(**(finance.values("expenses") | {"amount_kopecks": amount}))
            .returning(Expense.amount_kopecks)
        ).scalar_one()
        assert saved == amount


@pytest.mark.parametrize("table", TABLES)
def test_money_is_not_nullable(finance: FinanceDB, table: str) -> None:
    with pytest.raises(IntegrityError) as error, finance.engine.begin() as connection:
        connection.execute(
            Base.metadata.tables[table]
            .insert()
            .values(**(finance.values(table) | {"amount_kopecks": None}))
        )
    assert isinstance(error.value.orig, PostgreSQLError)
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == "amount_kopecks"


@pytest.mark.parametrize(
    ("identity", "constraint"),
    [
        ("member", "fk_settlements_sender_membership"),
        ("owner", "fk_settlements_receiver_membership"),
    ],
)
def test_settlement_alone_prevents_membership_deletion(
    finance: FinanceDB, identity: str, constraint: str
) -> None:
    # Remove expense children explicitly to isolate the settlement FK guarantee.
    with finance.engine.begin() as connection:
        for name in (
            "expense_item_shares",
            "expense_shares",
            "expense_items",
            "expenses",
        ):
            connection.execute(Base.metadata.tables[name].delete())
    with pytest.raises(IntegrityError) as error, finance.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM group_members WHERE group_id=:gid AND user_id=:uid"),
            {"gid": finance.group, "uid": getattr(finance, identity)},
        )
    assert isinstance(error.value.orig, PostgreSQLError)
    assert error.value.orig.diag.constraint_name == constraint
    with Session(finance.engine) as session:
        assert session.get(Settlement, finance.settlement) is not None
