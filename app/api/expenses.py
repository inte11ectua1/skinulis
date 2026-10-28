"""Thin sync Expense API with isolated verified public/internal actor channels."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.groups import ERRORS, no_store
from app.api.telegram_dependencies import get_bot_user
from app.db import get_session
from app.models import User
from app.schemas.expenses import (
    CreateInput,
    ExpenseMutation,
    ExpenseProfile,
    PreviewInput,
    PreviewProfile,
    QueryVersion,
    UpdateInput,
)
from app.schemas.groups import Page, PathId
from app.services import expense_crud

EXAMPLES = {
    "equal": {
        "summary": "100 RUB split among three members",
        "value": {
            "title": "Обед",
            "split_mode": "equal",
            "amount": "100.00",
            "participants": [2, 5, 10],
            "client_request_id": "00000000-0000-4000-8000-000000000004",
        },
    },
    "custom": {
        "summary": "Explicit shares including selected zero",
        "value": {
            "title": "Обед",
            "split_mode": "custom",
            "amount": "100.00",
            "shares": [
                {"user_id": 2, "amount": "0.00"},
                {"user_id": 5, "amount": "40.00"},
                {"user_id": 10, "amount": "60.00"},
            ],
            "client_request_id": "00000000-0000-4000-8000-000000000005",
        },
    },
}


def build_router(*, internal: bool = False) -> APIRouter:
    actor = get_bot_user if internal else get_current_user
    router = APIRouter(
        prefix="/internal" if internal else "",
        tags=["internal expenses" if internal else "expenses"],
        responses=ERRORS,
        dependencies=[Depends(no_store)],
    )

    @router.post("/groups/{group_id}/expenses/preview", response_model=PreviewProfile)
    def preview(
        group_id: PathId,
        payload: PreviewInput,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> PreviewProfile:
        """Read-only calculation, no UUID/storage/reservation. POST revalidates under lock."""
        return expense_crud.preview(session, group_id, user.id, payload.draft())

    @router.post(
        "/groups/{group_id}/expenses",
        status_code=201,
        response_model=ExpenseMutation,
        responses={
            200: {
                "model": ExpenseMutation,
                "description": "Original saved envelope for the same actor and normalized original intent",
            }
        },
        openapi_extra={
            "requestBody": {"content": {"application/json": {"examples": EXAMPLES}}}
        },
    )
    def create(
        group_id: PathId,
        payload: CreateInput,
        response: Response,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ExpenseMutation:
        """201 first create; 200 original replay even after PUT/DELETE. Keep UUID/body on timeout."""
        result, created = expense_crud.create(
            session, group_id, user.id, payload.client_request_id, payload.draft()
        )
        response.status_code = 201 if created else 200
        return result

    @router.get("/groups/{group_id}/expenses", response_model=Page[ExpenseProfile])
    def page(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[ExpenseProfile]:
        """Active saved snapshots, ascending (created_at,id), no total/has_next."""
        return Page(
            items=expense_crud.page(session, group_id, user.id, limit, offset),
            limit=limit,
            offset=offset,
        )

    @router.get("/expenses/{expense_id}", response_model=ExpenseProfile)
    def read(
        expense_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ExpenseProfile:
        """Membership only; unknown, foreign and soft-deleted expenses are hidden."""
        return expense_crud.read(session, user.id, expense_id)

    @router.put("/expenses/{expense_id}", response_model=ExpenseMutation)
    def update(
        expense_id: PathId,
        payload: UpdateInput,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ExpenseMutation:
        """Author-only full replacement; stale expected_version is 409. Read GET after timeout."""
        return expense_crud.update(
            session, user.id, expense_id, payload.expected_version, payload.draft()
        )

    @router.delete("/expenses/{expense_id}", response_model=ExpenseMutation)
    def remove(
        expense_id: PathId,
        expected_version: Annotated[QueryVersion, Query()],
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ExpenseMutation:
        """First DELETE checks version and increments it; author repeat preserves tombstone/version."""
        return expense_crud.remove(session, user.id, expense_id, expected_version)

    return router
