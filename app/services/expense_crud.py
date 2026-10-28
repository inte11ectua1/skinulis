"""Approved O-04 request transactions, original replay and optimistic writes."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Expense
from app.schemas.expenses import (
    ExpenseMutation,
    ExpenseProfile,
    PreviewProfile,
    ShareProfile,
)
from app.services import expenses
from app.services.expense_balances import mutation_balances
from app.services.expenses import (
    ByItemsExpense,
    CustomExpense,
    ExpenseInput,
    ExpenseSnapshot,
    PreparedExpense,
)
from app.services.groups import require_member
from app.services.money import format_money
from app.services.splits import SplitError
from app.services.transactions import write_transaction


def _prepare(session: Session, group_id: int, draft: ExpenseInput) -> PreparedExpense:
    if isinstance(draft, ByItemsExpense):
        raise ApiError(400, "validation_error", "Receipt HTTP contract awaits approval")
    members = expenses._members(session, group_id)
    ids = (
        [user_id for user_id, _ in draft.shares]
        if isinstance(draft, CustomExpense)
        else list(draft.participants)
    )
    if not set(ids) <= set(members):
        raise ApiError(
            400, "invalid_participants", "Select participants from this group"
        )
    try:
        return expenses.prepare_expense(draft, members)
    except (ValueError, TypeError) as error:
        raise ApiError(400, "validation_error", "Invalid expense data") from error


def _profile(value: ExpenseSnapshot) -> ExpenseProfile:
    return ExpenseProfile.model_validate(
        {
            "id": value.id,
            "group_id": value.group_id,
            "payer_id": value.payer_id,
            "client_request_id": value.client_request_id,
            "title": value.title,
            "split_mode": value.split_mode,
            "amount": format_money(value.amount_kopecks),
            "shares": [
                {"user_id": uid, "amount": format_money(amount)}
                for uid, amount in value.shares
            ],
            "created_at": value.created_at,
            "deleted_at": value.deleted_at,
            "version": value.version,
        }
    )


def _result(session: Session, value: ExpenseSnapshot) -> ExpenseMutation:
    # Serialize/validate inside the transaction; a bad snapshot rolls back the write.
    return ExpenseMutation(
        expense=_profile(value), balances=mutation_balances(session, value.group_id)
    )


def _intent(
    group_id: int, actor_id: int, draft: ExpenseInput, prepared: PreparedExpense
) -> dict[str, Any]:
    if isinstance(draft, ByItemsExpense):
        raise expenses.ExpenseDetailsUnsupported(
            "Ordered receipt intention awaits approval"
        )
    result: dict[str, Any] = dict(
        group_id=group_id,
        actor_id=actor_id,
        title=prepared.title,
        split_mode=prepared.split_mode,
        amount_kopecks=prepared.amount_kopecks,
    )
    if isinstance(draft, CustomExpense):
        result["shares"] = [[user_id, amount] for user_id, amount in prepared.shares]
    else:
        result["participants"] = [user_id for user_id, _ in prepared.shares]
    return result


def create(
    session: Session,
    group_id: int,
    actor_id: int,
    request_id: UUID,
    draft: ExpenseInput,
) -> tuple[ExpenseMutation, bool]:
    with write_transaction(session):
        require_member(session, group_id, actor_id, lock=True)
        previous = session.scalar(
            select(Expense)
            .where(
                Expense.group_id == group_id, Expense.client_request_id == request_id
            )
            .execution_options(populate_existing=True)
        )
        if previous is not None:
            if previous.payer_id != actor_id:
                raise ApiError(
                    409, "request_conflict", "Request key was used with different data"
                )
            if (
                previous.initial_create_intent is None
                or previous.initial_create_result is None
            ):
                raise ApiError(
                    409,
                    "request_history_unavailable",
                    "Original request history is unavailable",
                )
        prepared = _prepare(session, group_id, draft)
        intention = _intent(group_id, actor_id, draft, prepared)
        if previous is not None:
            if previous.initial_create_intent != intention:
                raise ApiError(
                    409, "request_conflict", "Request key was used with different data"
                )
            # Read the immutable ORIGINAL envelope, never current expense/shares/balances.
            return ExpenseMutation.model_validate(previous.initial_create_result), False
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
        expenses._insert_shares(session, expense, prepared)
        result = _result(session, expenses._snapshot(expense, prepared.shares))
        # The ONLY service assignments to history: first successful creation.
        expense.initial_create_intent = intention
        expense.initial_create_result = result.model_dump(mode="json")
        session.flush()
        return result, True


def preview(
    session: Session, group_id: int, actor_id: int, draft: ExpenseInput
) -> PreviewProfile:
    require_member(session, group_id, actor_id)
    value = _prepare(session, group_id, draft)
    if value.split_mode == "by_items":
        raise expenses.ExpenseDetailsUnsupported("Receipt preview DTO awaits approval")
    return PreviewProfile(
        group_id=group_id,
        payer_id=actor_id,
        title=value.title,
        split_mode=value.split_mode,
        amount=format_money(value.amount_kopecks),
        shares=[
            ShareProfile(user_id=uid, amount=format_money(amount))
            for uid, amount in value.shares
        ],
    )


def read(session: Session, actor_id: int, expense_id: int) -> ExpenseProfile:
    try:
        return _profile(expenses.read_expense(session, actor_id, expense_id))
    except expenses.ExpenseNotFound:
        raise ApiError(404, "expense_not_found", "Expense not found") from None


def page(
    session: Session, group_id: int, actor_id: int, limit: int, offset: int
) -> list[ExpenseProfile]:
    return [
        _profile(value)
        for value in expenses.list_expenses(
            session, group_id, actor_id, limit=limit, offset=offset
        )
    ]


def _version(expense: Expense, expected: int) -> None:
    if expense.version != expected:
        raise ApiError(
            409, "expense_version_conflict", "Expense changed; reload before editing"
        )
    if expense.version == 2**63 - 1:
        raise expenses.ExpenseSnapshotInvalid("Expense version cannot be advanced")
    expense.version += 1


def update(
    session: Session, actor_id: int, expense_id: int, expected: int, draft: ExpenseInput
) -> ExpenseMutation:
    try:
        with expenses.locked_edit(session, actor_id, expense_id) as editor:
            _version(editor._expense, expected)
            _prepare(session, editor._expense.group_id, draft)
            editor.replace_snapshot(draft)
            session.flush()
            return _result(session, editor.snapshot())
    except expenses.ExpenseNotFound:
        raise ApiError(404, "expense_not_found", "Expense not found") from None
    except expenses.ExpenseAuthorRequired:
        raise ApiError(
            403, "expense_author_required", "Only the expense author may change it"
        ) from None
    except (expenses.ExpenseDetailsUnsupported, SplitError):
        raise ApiError(400, "validation_error", "Invalid expense data") from None


def remove(
    session: Session, actor_id: int, expense_id: int, expected: int
) -> ExpenseMutation:
    try:
        with expenses.locked_edit(
            session, actor_id, expense_id, include_deleted=True
        ) as editor:
            if editor._expense.deleted_at is None:
                _version(editor._expense, expected)
            value = editor.mark_deleted()
            return _result(session, value)
    except expenses.ExpenseNotFound:
        raise ApiError(404, "expense_not_found", "Expense not found") from None
    except expenses.ExpenseAuthorRequired:
        raise ApiError(
            403, "expense_author_required", "Only the expense author may change it"
        ) from None
