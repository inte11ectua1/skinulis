"""Thin sync Expense API with isolated verified public/internal actor channels."""

from typing import Annotated, Any

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
    ExpenseResponse,
    PreviewInput,
    PreviewResponse,
    QueryVersion,
    UpdateInput,
)
from app.schemas.groups import Page, PathId
from app.services import expense_crud

EXAMPLES: dict[str, Any] = {
    "by_items": {
        "summary": "Receipt: per-item rounding, explicit zero selections",
        "value": {
            "title": "Чек",
            "split_mode": "by_items",
            "items": [{"title": "Чай", "amount": "0.01", "participants": [2, 5, 10]}],
            "client_request_id": "00000000-0000-4000-8000-000000000039",
        },
    },
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

    @router.post(
        "/groups/{group_id}/expenses/preview",
        response_model=PreviewResponse,
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            key: {
                                "summary": example["summary"],
                                "value": {
                                    field: value
                                    for field, value in example["value"].items()
                                    if field != "client_request_id"
                                },
                            }
                            for key, example in EXAMPLES.items()
                        }
                    }
                }
            }
        },
    )
    def preview(
        group_id: PathId,
        payload: PreviewInput,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> PreviewResponse:
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

    @router.get("/groups/{group_id}/expenses", response_model=Page[ExpenseResponse])
    def page(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[ExpenseResponse]:
        """Active saved snapshots, ascending (created_at,id), no total/has_next."""
        return Page(
            items=expense_crud.page(session, group_id, user.id, limit, offset),
            limit=limit,
            offset=offset,
        )

    @router.get("/expenses/{expense_id}", response_model=ExpenseResponse)
    def read(
        expense_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> ExpenseResponse:
        """Membership only; unknown, foreign and soft-deleted expenses are hidden."""
        return expense_crud.read(session, user.id, expense_id)

    @router.put(
        "/expenses/{expense_id}",
        response_model=ExpenseMutation,
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {
                        "examples": {
                            key: {
                                "summary": example["summary"],
                                "value": {
                                    field: value
                                    for field, value in example["value"].items()
                                    if field != "client_request_id"
                                }
                                | {"expected_version": 1},
                            }
                            for key, example in EXAMPLES.items()
                        }
                    }
                }
            }
        },
    )
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
