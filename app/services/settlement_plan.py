"""T-08 Q-05: fixed original ordering, no dynamic re-sort or persisted proposals."""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.services.expense_balances import calculate_balances
from app.services.expenses import ExpenseSnapshotInvalid
from app.services.groups import require_member
from app.services.splits import MAX_USER_ID


@dataclass(frozen=True, slots=True)
class Transfer:
    sender_id: int
    receiver_id: int
    amount_kopecks: int


def greedy_plan(balances: Mapping[int, int]) -> tuple[Transfer, ...]:
    if (
        any(
            type(uid) is not int
            or not 1 <= uid <= MAX_USER_ID
            or type(amount) is not int
            for uid, amount in balances.items()
        )
        or sum(balances.values()) != 0
    ):
        raise ExpenseSnapshotInvalid("Invalid balance vector")
    debtors = sorted(
        [[uid, -amount] for uid, amount in balances.items() if amount < 0],
        key=lambda row: (-row[1], row[0]),
    )
    creditors = sorted(
        [[uid, amount] for uid, amount in balances.items() if amount > 0],
        key=lambda row: (-row[1], row[0]),
    )
    i = j = 0
    result = []
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1])
        result.append(Transfer(debtors[i][0], creditors[j][0], amount))
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return tuple(result)


def read_balances(session: Session, group_id: int, actor_id: int) -> dict[int, int]:
    """Fresh read-only RR transaction, independent of dependency's autobegin.

    Membership, integrity validation and all ledger SELECTs share this snapshot.
    Never change the caller transaction/isolation or acquire group write locks.
    """
    bind = session.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            with Session(bind=connection) as reader:
                require_member(reader, group_id, actor_id)
                return calculate_balances(reader, group_id)
