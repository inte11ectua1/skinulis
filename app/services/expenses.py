"""O-04 calculations and locked primitives; expense_crud owns replay/version policy."""

from collections.abc import Collection, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from unicodedata import category, normalize
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.identity_tokens import utc_now
from app.models import Expense, ExpenseItem, ExpenseShare, GroupMember
from app.services.groups import require_member
from app.services.money import parse_money, validate_expense_amount
from app.services.splits import MAX_USER_ID, split_custom, split_equal
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


type ExpenseInput = EqualExpense | CustomExpense


@dataclass(frozen=True, slots=True)
class PreparedExpense:
    title: str
    split_mode: Literal["equal", "custom"]
    amount_kopecks: int
    shares: tuple[tuple[int, int], ...]


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


def _snapshot(expense: Expense, shares: Iterable[tuple[int, int]]) -> ExpenseSnapshot:
    saved_shares = tuple(shares)
    if (
        not saved_shares
        or sum(amount for _, amount in saved_shares) != expense.amount_kopecks
    ):
        raise ExpenseSnapshotInvalid("Stored expense snapshot is inconsistent")
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
        return _snapshot(expense, prepared.shares)


def read_expense(session: Session, actor_id: int, expense_id: int) -> ExpenseSnapshot:
    _identifier(actor_id)
    _identifier(expense_id)
    # One SQL snapshot for metadata AND shares: a concurrent replacement cannot
    # leave a reader with old metadata and new shares from a second SELECT.
    rows = session.execute(
        select(Expense, ExpenseShare)
        .join(
            GroupMember,
            (GroupMember.group_id == Expense.group_id)
            & (GroupMember.user_id == actor_id),
        )
        .outerjoin(ExpenseShare, ExpenseShare.expense_id == Expense.id)
        .where(Expense.id == expense_id, Expense.deleted_at.is_(None))
        .order_by(ExpenseShare.user_id)
        .execution_options(populate_existing=True)
    ).all()
    if not rows:
        raise ExpenseNotFound("Expense not found")
    return _snapshot(
        rows[0][0],
        (
            (share.user_id, share.amount_kopecks)
            for _, share in rows
            if share is not None
        ),
    )


def list_expenses(
    session: Session, group_id: int, actor_id: int, *, limit: int = 20, offset: int = 0
) -> list[ExpenseSnapshot]:
    _identifier(group_id)
    _identifier(actor_id)
    if type(limit) is not int or type(offset) is not int or limit < 1 or offset < 0:
        raise ValueError("Invalid internal pagination")
    # HTTP schemas enforce the approved page bounds; this helper also serves tests.
    require_member(session, group_id, actor_id)
    # No group can contain more than positive signed BIGINT expense IDs. Avoid
    # narrowing an arbitrary non-negative public offset into PostgreSQL BIGINT.
    if offset > MAX_USER_ID:
        return []
    page = (
        select(Expense.id)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(Expense.created_at, Expense.id)
        .limit(limit)
        .offset(offset)
        .subquery()
    )
    rows = session.execute(
        select(Expense, ExpenseShare)
        .join(page, page.c.id == Expense.id)
        .outerjoin(ExpenseShare, ExpenseShare.expense_id == Expense.id)
        .order_by(Expense.created_at, Expense.id, ExpenseShare.user_id)
        .execution_options(populate_existing=True)
    ).all()
    values: dict[int, tuple[Expense, list[tuple[int, int]]]] = {}
    for expense, share in rows:
        if expense.id not in values:
            values[expense.id] = (expense, [])
        if share is not None:
            values[expense.id][1].append((share.user_id, share.amount_kopecks))
    return [_snapshot(expense, shares) for expense, shares in values.values()]


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
        shares = self._session.execute(
            select(ExpenseShare.user_id, ExpenseShare.amount_kopecks)
            .where(ExpenseShare.expense_id == self._expense.id)
            .order_by(ExpenseShare.user_id)
        )
        return _snapshot(
            self._expense, ((user_id, amount) for user_id, amount in shares)
        )

    def replace_snapshot(self, draft: ExpenseInput) -> ExpenseSnapshot:
        """Atomic primitive AFTER expense_crud has checked the expected version."""
        self._check_scope()
        expense, session = self._expense, self._session
        if expense.deleted_at is not None:
            raise ExpenseNotFound("Expense not found")
        if (
            expense.split_mode not in ("equal", "custom")
            or session.scalar(
                select(ExpenseItem.id)
                .where(ExpenseItem.expense_id == expense.id)
                .limit(1)
            )
            is not None
        ):
            raise ExpenseDetailsUnsupported("Receipt replacement belongs to O-05")
        prepared = prepare_expense(draft, _members(session, expense.group_id))
        session.execute(
            delete(ExpenseShare).where(ExpenseShare.expense_id == expense.id)
        )
        expense.title, expense.split_mode = prepared.title, prepared.split_mode
        expense.amount_kopecks = prepared.amount_kopecks
        _insert_shares(session, expense, prepared)
        return _snapshot(expense, prepared.shares)

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
