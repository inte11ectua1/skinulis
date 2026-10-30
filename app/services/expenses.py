"""O-04/O-05 calculations and locked storage; expense_crud owns replay/version policy."""

from collections.abc import Collection, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from unicodedata import category, normalize
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    String,
    cast,
    delete,
    literal,
    null,
    select,
    union_all,
)
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.errors import ApiError
from app.core.identity_tokens import utc_now
from app.models import Expense, ExpenseItem, ExpenseItemShare, ExpenseShare, GroupMember
from app.services.groups import require_member
from app.services.money import parse_money, validate_expense_amount
from app.services.splits import (
    MAX_ITEMS,
    MAX_USER_ID,
    SplitError,
    split_custom,
    split_equal,
)
from app.services.transactions import write_transaction


class ExpenseNotFound(LookupError):
    """Unknown, foreign or deleted expense; contains no expense information."""


class ExpenseAuthorRequired(PermissionError):
    """A member (including the group owner) cannot change another author's expense."""


class ExpenseRequestExists(RuntimeError):
    """Occupied UUID in the low-level first-insert helper; HTTP uses expense_crud."""


class ExpenseDetailsUnsupported(ValueError):
    """O-04 must not replace a receipt or discard its nested financial history."""


class ExpenseSnapshotInvalid(RuntimeError):
    """Persisted totals are inconsistent; never silently repair them."""


@dataclass(frozen=True, slots=True)
class EqualExpense:
    """Internal Python input in RUB strings; no JSON/schema or actor fields."""

    title: str
    amount: str
    participants: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CustomExpense:
    title: str
    amount: str
    shares: tuple[tuple[int, str], ...]


@dataclass(frozen=True, slots=True)
class ReceiptItemInput:
    """Internal ordered item; HTTP validation lives in schemas.expenses."""

    title: str
    amount: str
    participants: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ByItemsExpense:
    title: str
    items: tuple[ReceiptItemInput, ...]


type ExpenseInput = EqualExpense | CustomExpense | ByItemsExpense


@dataclass(frozen=True, slots=True)
class PreparedExpenseItem:
    position: int
    title: str
    amount_kopecks: int
    shares: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class ExpenseItemSnapshot:
    id: int
    position: int
    title: str
    amount_kopecks: int
    shares: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class PreparedExpense:
    title: str
    split_mode: Literal["equal", "custom", "by_items"]
    amount_kopecks: int
    shares: tuple[tuple[int, int], ...]
    items: tuple[PreparedExpenseItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpenseSnapshot:
    """Immutable internal copy; no promise about HTTP fields or wire serialization."""

    id: int
    group_id: int
    payer_id: int
    title: str
    split_mode: str
    amount_kopecks: int
    client_request_id: UUID
    created_at: datetime
    deleted_at: datetime | None
    shares: tuple[tuple[int, int], ...]
    version: int
    items: tuple[ExpenseItemSnapshot, ...] = ()


def normalize_title(value: str) -> str:
    """Q-03 approved in #23: NFC, Unicode strip, code points, then category C."""
    if not isinstance(value, str):
        raise TypeError("Expense title must be a string")
    title = normalize("NFC", value).strip()
    if not 1 <= len(title) <= 120 or any(
        category(char).startswith("C") for char in title
    ):
        raise ValueError("Use 1–120 characters without control characters")
    return title


def prepare_expense(draft: ExpenseInput, members: Collection[int]) -> PreparedExpense:
    title = normalize_title(draft.title)
    if isinstance(draft, ByItemsExpense):
        if not 1 <= len(draft.items) <= MAX_ITEMS:
            raise SplitError("A receipt must contain between 1 and 50 items")
        total = 0
        combined: dict[int, int] = {}
        items: list[PreparedExpenseItem] = []
        for position, item in enumerate(draft.items, 1):
            item_title = normalize_title(item.title)
            amount = validate_expense_amount(parse_money(item.amount))
            shares = split_equal(amount, item.participants, group_members=members)
            total += amount
            validate_expense_amount(total)
            for user_id, share in shares.items():
                combined[user_id] = combined.get(user_id, 0) + share
            items.append(
                PreparedExpenseItem(position, item_title, amount, tuple(shares.items()))
            )
        return PreparedExpense(
            title, "by_items", total, tuple(sorted(combined.items())), tuple(items)
        )
    amount = validate_expense_amount(parse_money(draft.amount))
    if isinstance(draft, EqualExpense):
        mode: Literal["equal", "custom"] = "equal"
        shares = split_equal(amount, draft.participants, group_members=members)
    else:
        mode = "custom"
        shares = split_custom(
            amount,
            [(user_id, parse_money(value)) for user_id, value in draft.shares],
            group_members=members,
        )
    return PreparedExpense(title, mode, amount, tuple(shares.items()))


def _identifier(value: int) -> None:
    if type(value) is not int or not 1 <= value <= MAX_USER_ID:
        raise ValueError("Identifier must be a positive signed BIGINT integer")


def _members(session: Session, group_id: int) -> list[int]:
    return list(
        session.scalars(
            select(GroupMember.user_id).where(GroupMember.group_id == group_id)
        )
    )


def _snapshot(
    expense: Expense,
    shares: Iterable[tuple[int, int]],
    items: tuple[ExpenseItemSnapshot, ...] = (),
) -> ExpenseSnapshot:
    saved_shares = tuple(shares)
    if (
        not saved_shares
        or sum(amount for _, amount in saved_shares) != expense.amount_kopecks
    ):
        raise ExpenseSnapshotInvalid("Stored expense snapshot is inconsistent")
    if expense.split_mode == "by_items":
        if not 1 <= len(items) <= MAX_ITEMS:
            raise ExpenseSnapshotInvalid("Stored receipt item set is inconsistent")
        combined: dict[int, int] = {}
        for item in items:
            if (
                not item.shares
                or sum(amount for _, amount in item.shares) != item.amount_kopecks
            ):
                raise ExpenseSnapshotInvalid("Stored item snapshot is inconsistent")
            for user_id, amount in item.shares:
                combined[user_id] = combined.get(user_id, 0) + amount
        if (
            sum(item.amount_kopecks for item in items) != expense.amount_kopecks
            or tuple(sorted(combined.items())) != saved_shares
        ):
            raise ExpenseSnapshotInvalid("Stored final and item snapshots disagree")
    elif items:
        raise ExpenseSnapshotInvalid("Unexpected receipt details for a simple expense")
    return ExpenseSnapshot(
        expense.id,
        expense.group_id,
        expense.payer_id,
        expense.title,
        expense.split_mode,
        expense.amount_kopecks,
        expense.client_request_id,
        expense.created_at,
        expense.deleted_at,
        saved_shares,
        expense.version,
        items,
    )


def _insert_shares(
    session: Session, expense: Expense, prepared: PreparedExpense
) -> None:
    session.add_all(
        ExpenseShare(
            expense_id=expense.id,
            group_id=expense.group_id,
            user_id=user_id,
            amount_kopecks=amount,
        )
        for user_id, amount in prepared.shares
    )
    session.flush()
    if prepared.items:
        items = [
            ExpenseItem(
                expense_id=expense.id,
                group_id=expense.group_id,
                title=item.title,
                amount_kopecks=item.amount_kopecks,
                position=item.position,
            )
            for item in prepared.items
        ]
        session.add_all(items)
        session.flush()
        session.add_all(
            ExpenseItemShare(
                item_id=stored.id,
                expense_id=expense.id,
                group_id=expense.group_id,
                user_id=user_id,
                amount_kopecks=amount,
            )
            for stored, item in zip(items, prepared.items, strict=True)
            for user_id, amount in item.shares
        )
        session.flush()


def create_once(
    session: Session,
    group_id: int,
    actor_id: int,
    request_id: UUID,
    draft: ExpenseInput,
) -> ExpenseSnapshot:
    """Low-level first insertion for internal/legacy fixtures, without replay history.

    Production routers use expense_crud.create with original intent/result storage.
    Never infer a replay from this helper or supply an actor from public JSON.
    """
    with write_transaction(session):
        _identifier(group_id)
        _identifier(actor_id)
        if not isinstance(request_id, UUID):
            raise TypeError("Request key must be a UUID")
        with session.no_autoflush:
            require_member(session, group_id, actor_id, lock=True)
        if (
            session.scalar(
                select(Expense.id).where(
                    Expense.group_id == group_id,
                    Expense.client_request_id == request_id,
                )
            )
            is not None
        ):
            raise ExpenseRequestExists(
                "Request key exists; use the original-request replay service"
            )
        prepared = prepare_expense(draft, _members(session, group_id))
        expense = Expense(
            group_id=group_id,
            payer_id=actor_id,
            client_request_id=request_id,
            title=prepared.title,
            split_mode=prepared.split_mode,
            amount_kopecks=prepared.amount_kopecks,
        )
        session.add(expense)
        session.flush()
        _insert_shares(session, expense, prepared)
        if prepared.items:
            return _read_snapshots(
                session, select(Expense.id).where(Expense.id == expense.id)
            )[0]
        return _snapshot(expense, prepared.shares)


def _read_snapshots(session: Session, selected: Select[int]) -> list[ExpenseSnapshot]:
    """One MVCC snapshot, no final-share × item-share Cartesian product.

    Materialize only page IDs, then append final/detail rows with UNION ALL.
    Network/database statement count does not grow with receipts or positions.
    """
    page = selected.cte("expense_page")
    details = union_all(
        select(
            ExpenseShare.expense_id,
            literal("final", String).label("kind"),
            cast(null(), BigInteger).label("item_id"),
            cast(null(), BigInteger).label("position"),
            cast(null(), String).label("title"),
            cast(null(), BigInteger).label("item_amount"),
            ExpenseShare.user_id,
            ExpenseShare.amount_kopecks.label("share_amount"),
        ).join(page, page.c.id == ExpenseShare.expense_id),
        select(
            ExpenseItem.expense_id,
            literal("item", String),
            ExpenseItem.id,
            ExpenseItem.position,
            ExpenseItem.title,
            ExpenseItem.amount_kopecks,
            ExpenseItemShare.user_id,
            ExpenseItemShare.amount_kopecks,
        )
        .join(page, page.c.id == ExpenseItem.expense_id)
        .outerjoin(ExpenseItemShare, ExpenseItemShare.item_id == ExpenseItem.id),
    ).subquery("financial_rows")
    rows = session.execute(
        select(
            Expense,
            details.c.kind,
            details.c.item_id,
            details.c.position,
            details.c.title,
            details.c.item_amount,
            details.c.user_id,
            details.c.share_amount,
        )
        .join(page, page.c.id == Expense.id)
        .outerjoin(details, details.c.expense_id == Expense.id)
        .order_by(
            Expense.created_at,
            Expense.id,
            details.c.kind,
            details.c.position,
            details.c.user_id,
        )
        .execution_options(populate_existing=True)
    )
    values: dict[
        int,
        tuple[
            Expense,
            list[tuple[int, int]],
            dict[tuple[int, int, str, int], list[tuple[int, int]]],
        ],
    ] = {}
    for (
        expense,
        kind,
        item_id,
        position,
        title,
        item_amount,
        user_id,
        share_amount,
    ) in rows:
        entry = values.setdefault(expense.id, (expense, [], {}))
        if kind == "final":
            entry[1].append((user_id, share_amount))
        elif kind == "item":
            item_shares = entry[2].setdefault(
                (item_id, position, title, item_amount), []
            )
            if user_id is not None:
                item_shares.append((user_id, share_amount))
    return [
        _snapshot(
            expense,
            shares,
            tuple(
                ExpenseItemSnapshot(
                    item_id, position, title, amount, tuple(item_shares)
                )
                for (item_id, position, title, amount), item_shares in items.items()
            ),
        )
        for expense, shares, items in values.values()
    ]


def validate_receipts(session: Session, group_id: int) -> None:
    """Validate stored details against final snapshots; never redistribute shares."""
    _read_snapshots(
        session,
        select(Expense.id).where(
            Expense.group_id == group_id,
            Expense.deleted_at.is_(None),
            Expense.split_mode == "by_items",
        ),
    )


def read_expense(session: Session, actor_id: int, expense_id: int) -> ExpenseSnapshot:
    _identifier(actor_id)
    _identifier(expense_id)
    values = _read_snapshots(
        session,
        select(Expense.id)
        .join(
            GroupMember,
            (GroupMember.group_id == Expense.group_id)
            & (GroupMember.user_id == actor_id),
        )
        .where(Expense.id == expense_id, Expense.deleted_at.is_(None)),
    )
    if not values:
        raise ExpenseNotFound("Expense not found")
    return values[0]


def list_expenses(
    session: Session, group_id: int, actor_id: int, *, limit: int = 20, offset: int = 0
) -> list[ExpenseSnapshot]:
    _identifier(group_id)
    _identifier(actor_id)
    if type(limit) is not int or type(offset) is not int or limit < 1 or offset < 0:
        raise ValueError("Invalid internal pagination")
    require_member(session, group_id, actor_id)
    if offset > MAX_USER_ID:
        return []
    return _read_snapshots(
        session,
        select(Expense.id)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(Expense.created_at, Expense.id)
        .limit(limit)
        .offset(offset),
    )


class _ExpenseEditor:
    """Group-locked primitives; expense_crud enforces the approved version policy."""

    def __init__(self, session: Session, expense: Expense) -> None:
        self._session = session
        self._expense = expense
        self._transaction = session.get_transaction()
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def _check_scope(self) -> None:
        if (
            self._closed
            or self._transaction is None
            or not self._transaction.is_active
            or self._session.get_transaction() is not self._transaction
        ):
            raise RuntimeError(
                "Expense editor requires its original locked transaction"
            )

    def snapshot(self) -> ExpenseSnapshot:
        self._check_scope()
        return _read_snapshots(
            self._session, select(Expense.id).where(Expense.id == self._expense.id)
        )[0]

    def replace_snapshot(
        self, draft: ExpenseInput, *, allow_receipt: bool = False
    ) -> ExpenseSnapshot:
        """Storage replacement; HTTP opts in only after author/version verification.

        Internal callers retain an explicit guard against accidental detail loss.
        All mode transitions are approved by T-07 issue39/6473059675.
        """
        self._check_scope()
        expense, session = self._expense, self._session
        if expense.deleted_at is not None:
            raise ExpenseNotFound("Expense not found")
        has_items = (
            expense.split_mode == "by_items"
            or session.scalar(
                select(ExpenseItem.id)
                .where(ExpenseItem.expense_id == expense.id)
                .limit(1)
            )
            is not None
        )
        if (has_items or isinstance(draft, ByItemsExpense)) and not allow_receipt:
            raise ExpenseDetailsUnsupported(
                "Receipt replacement requires explicit caller opt-in"
            )
        prepared = prepare_expense(draft, _members(session, expense.group_id))
        # Every saved mode must be valid before replacement can erase its evidence.
        # Validate under the existing group/expense locks; failure rolls back version.
        self.snapshot()
        if has_items:
            session.execute(
                delete(ExpenseItemShare).where(
                    ExpenseItemShare.expense_id == expense.id
                )
            )
            session.execute(
                delete(ExpenseItem).where(ExpenseItem.expense_id == expense.id)
            )
        session.execute(
            delete(ExpenseShare).where(ExpenseShare.expense_id == expense.id)
        )
        expense.title, expense.split_mode = prepared.title, prepared.split_mode
        expense.amount_kopecks = prepared.amount_kopecks
        _insert_shares(session, expense, prepared)
        return self.snapshot()

    def mark_deleted(self) -> ExpenseSnapshot:
        """Set the tombstone once; keep all shares/items/settlements unchanged."""
        self._check_scope()
        if self._expense.deleted_at is None:
            self._expense.deleted_at = utc_now()
        self._session.flush()
        return self.snapshot()


@contextmanager
def locked_edit(
    session: Session, actor_id: int, expense_id: int, *, include_deleted: bool = False
) -> Iterator[_ExpenseEditor]:
    """Own one transaction, group first, refreshed expense second, author only.

    expense_crud owns approved HTTP version/replay policy in this scope;
    callers must never use this low-level helper as unconditional public PUT.
    """
    with write_transaction(session):
        _identifier(actor_id)
        _identifier(expense_id)
        with session.no_autoflush:
            group_id = session.scalar(
                select(Expense.group_id).where(Expense.id == expense_id)
            )
            if group_id is None:
                raise ExpenseNotFound("Expense not found")
            try:
                require_member(session, group_id, actor_id, lock=True)
            except ApiError as error:
                if error.status == 404:
                    raise ExpenseNotFound("Expense not found") from None
                raise
            expense = session.scalar(
                select(Expense)
                .where(Expense.id == expense_id, Expense.group_id == group_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        if expense is None or (expense.deleted_at is not None and not include_deleted):
            raise ExpenseNotFound("Expense not found")
        if expense.payer_id != actor_id:
            raise ExpenseAuthorRequired("Only the expense author may change it")
        editor = _ExpenseEditor(session, expense)
        try:
            yield editor
        finally:
            editor.close()
