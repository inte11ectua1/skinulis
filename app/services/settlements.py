"""Manual settlements: group-first writes, original replay and fresh confirm checks."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.identity_tokens import utc_now
from app.models import GroupMember, Settlement
from app.schemas.settlements import (
    Direction,
    SettlementCreate,
    SettlementMutation,
    SettlementProfile,
    SettlementStatus,
)
from app.services.expense_balances import calculate_balances
from app.services.groups import require_member
from app.services.money import format_money, parse_money
from app.services.transactions import write_transaction

Action = Literal["confirm", "reject", "cancel"]
TARGET: dict[Action, SettlementStatus] = {
    "confirm": "confirmed",
    "reject": "rejected",
    "cancel": "cancelled",
}


@dataclass(frozen=True, slots=True)
class Intent:
    group_id: int
    sender_id: int
    receiver_id: int
    amount_kopecks: int


def normalize_intent(group_id: int, actor_id: int, draft: SettlementCreate) -> Intent:
    return Intent(
        group_id,
        actor_id,
        draft.receiver_id,
        parse_money(draft.amount, minimum=1, maximum=2**63 - 1),
    )


def require_role(
    action: Action, actor_id: int, sender_id: int, receiver_id: int
) -> None:
    if action == "cancel":
        if actor_id != sender_id:
            raise ApiError(
                403, "settlement_sender_required", "Only the sender may cancel"
            )
    elif actor_id != receiver_id:
        raise ApiError(
            403, "settlement_receiver_required", "Only the receiver may resolve"
        )


def check_balance(balances: dict[int, int], intent: Intent) -> None:
    debt = -balances[intent.sender_id]
    credit = balances[intent.receiver_id]
    if debt <= 0 or credit <= 0 or not 0 < intent.amount_kopecks <= min(debt, credit):
        raise ApiError(
            409,
            "settlement_balance_conflict",
            "Current balances do not allow this settlement",
        )


def _profile(row: Settlement, *, original: bool = False) -> SettlementProfile:
    # Only status/resolved_at can change in this service. No JSONB history needed.
    return SettlementProfile.model_validate(
        dict(
            id=row.id,
            group_id=row.group_id,
            sender_id=row.sender_id,
            receiver_id=row.receiver_id,
            amount=format_money(row.amount_kopecks),
            status="pending" if original else row.status,
            client_request_id=row.client_request_id,
            created_at=row.created_at,
            resolved_at=None if original else row.resolved_at,
        )
    )


def create(
    session: Session, group_id: int, actor_id: int, draft: SettlementCreate
) -> tuple[SettlementMutation, bool]:
    with write_transaction(session):
        require_member(session, group_id, actor_id, lock=True)
        intent = normalize_intent(group_id, actor_id, draft)
        previous = session.scalar(
            select(Settlement)
            .where(
                Settlement.group_id == group_id,
                Settlement.client_request_id == draft.client_request_id,
            )
            .execution_options(populate_existing=True)
        )
        if previous is not None:
            if intent != Intent(
                previous.group_id,
                previous.sender_id,
                previous.receiver_id,
                previous.amount_kopecks,
            ):
                raise ApiError(
                    409, "request_conflict", "Request key was used with different data"
                )
            return SettlementMutation(
                settlement=_profile(previous, original=True)
            ), False
        if (
            intent.receiver_id == actor_id
            or session.get(GroupMember, (group_id, intent.receiver_id)) is None
        ):
            raise ApiError(
                400, "invalid_participants", "Select another member of this group"
            )
        check_balance(calculate_balances(session, group_id), intent)
        row = Settlement(
            group_id=group_id,
            sender_id=actor_id,
            receiver_id=intent.receiver_id,
            amount_kopecks=intent.amount_kopecks,
            client_request_id=draft.client_request_id,
            status="pending",
        )
        session.add(row)
        session.flush()
        return SettlementMutation(settlement=_profile(row, original=True)), True


def resolve(
    session: Session, settlement_id: int, actor_id: int, action: Action
) -> SettlementMutation:
    with write_transaction(session):
        with session.no_autoflush:
            # A non-authorizing lookup: no settlement lock before the group lock.
            group_id = session.scalar(
                select(Settlement.group_id).where(Settlement.id == settlement_id)
            )
            if group_id is None:
                raise ApiError(404, "settlement_not_found", "Settlement not found")
            try:
                require_member(session, group_id, actor_id, lock=True)
            except ApiError as error:
                if error.status == 404:
                    raise ApiError(
                        404, "settlement_not_found", "Settlement not found"
                    ) from None
                raise
            row = session.scalar(
                select(Settlement)
                .where(
                    Settlement.id == settlement_id,
                    Settlement.group_id == group_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        if row is None:
            raise ApiError(404, "settlement_not_found", "Settlement not found")
        # Check role even for terminal repeats, before revealing status.
        require_role(action, actor_id, row.sender_id, row.receiver_id)
        target = TARGET[action]
        if row.status == target:
            return SettlementMutation(settlement=_profile(row))
        if row.status != "pending":
            raise ApiError(
                409, "settlement_state_conflict", "Settlement is already resolved"
            )
        if action == "confirm":
            check_balance(
                calculate_balances(session, group_id),
                Intent(
                    group_id,
                    row.sender_id,
                    row.receiver_id,
                    row.amount_kopecks,
                ),
            )
        # The only updates to existing settlements; immutable creation fields stay intact.
        row.status = target
        row.resolved_at = max(utc_now(), row.created_at)
        session.flush()
        return SettlementMutation(settlement=_profile(row))


def page(
    session: Session,
    group_id: int,
    actor_id: int,
    limit: int,
    offset: int,
    status: SettlementStatus | None = None,
    direction: Direction = "all",
) -> list[SettlementProfile]:
    require_member(session, group_id, actor_id)
    query = select(Settlement).where(Settlement.group_id == group_id)
    if status is not None:
        query = query.where(Settlement.status == status)
    if direction == "incoming":
        query = query.where(Settlement.receiver_id == actor_id)
    elif direction == "outgoing":
        query = query.where(Settlement.sender_id == actor_id)
    return [
        _profile(row)
        for row in session.scalars(
            query.order_by(Settlement.created_at, Settlement.id)
            .limit(limit)
            .offset(offset)
        )
    ]
