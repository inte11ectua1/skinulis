"""Thin sync T-08 routes using the existing isolated JWT/service actor channels."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.groups import ERRORS, no_store
from app.api.telegram_dependencies import get_bot_user
from app.db import get_session
from app.models import User
from app.schemas.groups import EmptyInput, Page, PathId
from app.schemas.settlements import (
    Direction,
    SettlementCreate,
    SettlementMutation,
    SettlementProfile,
    SettlementStatus,
)
from app.services import settlements


def settlement_headers(response: Response) -> None:
    no_store(response)
    response.headers["X-Request-ID"] = str(uuid4())


def build_router(*, internal: bool = False) -> APIRouter:
    actor = get_bot_user if internal else get_current_user
    router = APIRouter(
        prefix="/internal" if internal else "",
        tags=["settlements"],
        responses=ERRORS,
        dependencies=[Depends(settlement_headers)],
    )

    @router.post(
        "/groups/{group_id}/settlements",
        status_code=201,
        response_model=SettlementMutation,
        responses={
            200: {
                "model": SettlementMutation,
                "description": "Original pending creation replay, not current status",
            }
        },
    )
    def create(
        group_id: PathId,
        payload: SettlementCreate,
        response: Response,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> SettlementMutation:
        """Manual external transfer notice. Retry same UUID/body after timeout; GET for current status."""
        result, created = settlements.create(session, group_id, user.id, payload)
        response.status_code = 201 if created else 200
        return result

    @router.get(
        "/groups/{group_id}/settlements", response_model=Page[SettlementProfile]
    )
    def page(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        status: SettlementStatus | None = None,
        direction: Direction = "all",
    ) -> Page[SettlementProfile]:
        """Current statuses; filters precede pagination, ascending (created_at,id)."""
        return Page(
            items=settlements.page(
                session, group_id, user.id, limit, offset, status, direction
            ),
            limit=limit,
            offset=offset,
        )

    @router.post(
        "/settlements/{settlement_id}/confirm", response_model=SettlementMutation
    )
    def confirm(
        settlement_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        payload: Annotated[EmptyInput | None, Body()] = None,
    ) -> SettlementMutation:
        """Receiver only. Fresh debt/credit under group lock; same terminal retry is a no-op."""
        return settlements.resolve(session, settlement_id, user.id, "confirm")

    @router.post(
        "/settlements/{settlement_id}/reject", response_model=SettlementMutation
    )
    def reject(
        settlement_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        payload: Annotated[EmptyInput | None, Body()] = None,
    ) -> SettlementMutation:
        """Receiver only; does not change balances."""
        return settlements.resolve(session, settlement_id, user.id, "reject")

    @router.post(
        "/settlements/{settlement_id}/cancel", response_model=SettlementMutation
    )
    def cancel(
        settlement_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        payload: Annotated[EmptyInput | None, Body()] = None,
    ) -> SettlementMutation:
        """Sender only; does not change balances."""
        return settlements.resolve(session, settlement_id, user.id, "cancel")

    return router
