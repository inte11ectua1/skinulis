"""Shared business operations with explicitly separate public and service actors."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.telegram_dependencies import get_bot_user
from app.db import get_session
from app.models import User
from app.schemas.groups import (
    CapabilityInput,
    GroupCreate,
    GroupProfile,
    InviteIssued,
    MemberProfile,
    Page,
    PathId,
    RequestKey,
)
from app.schemas.system import ErrorResponse
from app.services import groups

ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 500, "4XX")
}


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def build_router(*, internal: bool = False) -> APIRouter:
    actor = get_bot_user if internal else get_current_user
    router = APIRouter(
        prefix="/internal" if internal else "",
        tags=[
            "groups (proposed T-06)"
            if not internal
            else "internal groups (proposed T-06)"
        ],
        responses=ERRORS,
        dependencies=[Depends(no_store)],
    )

    @router.post("/groups", status_code=201, response_model=GroupProfile)
    def create(
        payload: GroupCreate,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> GroupProfile:
        """Create with owner membership; replay the same UUID/body after timeout."""
        return GroupProfile.model_validate(
            groups.create_group(
                session, user.id, payload.name, payload.client_request_id
            )
        )

    @router.get("/groups", response_model=Page[GroupProfile])
    def mine(
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[GroupProfile]:
        return Page(
            items=[
                GroupProfile.model_validate(group)
                for group in groups.list_groups(session, user.id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )

    @router.get("/groups/{group_id}", response_model=GroupProfile)
    def read(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> GroupProfile:
        """404 also hides existing groups from non-members."""
        return GroupProfile.model_validate(
            groups.require_member(session, group_id, user.id)
        )

    @router.get("/groups/{group_id}/members", response_model=Page[MemberProfile])
    def members(
        group_id: PathId,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[MemberProfile]:
        group = groups.require_member(session, group_id, user.id)
        return Page(
            items=[
                MemberProfile(
                    user_id=member.user_id,
                    joined_at=member.joined_at,
                    is_owner=member.user_id == group.owner_id,
                )
                for member in groups.list_members(session, group_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )

    @router.post(
        "/groups/{group_id}/invites", status_code=201, response_model=InviteIssued
    )
    def invite(
        group_id: PathId,
        payload: RequestKey,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> InviteIssued:
        """Owner only. Raw token is issued once; replay returns token=null."""
        value, raw = groups.issue_invite(
            session, group_id, user.id, payload.client_request_id
        )
        return InviteIssued(
            **{
                key: getattr(value, key)
                for key in InviteIssued.model_fields
                if key != "token"
            },
            token=raw,
        )

    @router.post("/group-invites/join", response_model=GroupProfile)
    def join(
        payload: CapabilityInput,
        user: Annotated[User, Depends(actor)],
        session: Annotated[Session, Depends(get_session)],
    ) -> GroupProfile:
        """Voluntary join. Invalid/expired/used/revoked tokens share a safe 404."""
        return GroupProfile.model_validate(
            groups.join_group(session, user.id, payload.token.get_secret_value())
        )

    return router
