"""O-06 read-only endpoints with existing isolated actor channels."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.groups import ERRORS, no_store
from app.api.telegram_dependencies import get_bot_user
from app.db import get_session
from app.models import User
from app.schemas.balances import BalancesResponse, PlanResponse, TransferProfile
from app.schemas.groups import PathId
from app.services.expense_balances import profiles
from app.services.money import format_money
from app.services.settlement_plan import greedy_plan, read_balances


def build_router(*, internal: bool = False) -> APIRouter:
    actor = get_bot_user if internal else get_current_user
    router = APIRouter(
        prefix="/internal" if internal else "",
        tags=["balances"],
        responses=ERRORS,
        dependencies=[Depends(no_store)],
    )

    @router.get("/groups/{group_id}/balances", response_model=BalancesResponse)
    def balances(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> BalancesResponse:
        return BalancesResponse(
            group_id=group_id,
            balances=profiles(read_balances(session, group_id, user.id)),
        )

    @router.get("/groups/{group_id}/settlement-plan", response_model=PlanResponse)
    def plan(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> PlanResponse:
        vector = read_balances(session, group_id, user.id)
        return PlanResponse(
            group_id=group_id,
            transfers=[
                TransferProfile(
                    sender_id=t.sender_id,
                    receiver_id=t.receiver_id,
                    amount=format_money(t.amount_kopecks),
                )
                for t in greedy_plan(vector)
            ],
        )

    return router
