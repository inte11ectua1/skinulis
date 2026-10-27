"""One request transaction per write; group lock always precedes invite/member locks."""

from datetime import timedelta
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.identity_tokens import new_secret, secret_digest, utc_now
from app.models import Group, GroupInvite, GroupMember
from app.services.transactions import write_transaction


def require_member(
    session: Session, group_id: int, user_id: int, *, lock: bool = False
) -> Group:
    query = select(Group).where(Group.id == group_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    group = session.scalar(query)
    if group is None or session.get(GroupMember, (group_id, user_id)) is None:
        raise ApiError(404, "group_not_found", "Group not found")
    return group


def require_owner(group: Group, user_id: int) -> None:
    if group.owner_id != user_id:
        raise ApiError(
            403, "owner_required", "Only the group owner can manage invitations"
        )


def _same_group(group: Group, name: str) -> Group:
    if group.name != name:
        raise ApiError(
            409, "request_conflict", "Request key was used with different data"
        )
    return group


def create_group(session: Session, user_id: int, name: str, request_id: UUID) -> Group:
    query = select(Group).where(
        Group.owner_id == user_id, Group.client_request_id == request_id
    )
    try:
        with write_transaction(session):
            previous = session.scalar(query)
            if previous is not None:
                return _same_group(previous, name)
            group = Group(owner_id=user_id, name=name, client_request_id=request_id)
            session.add(group)
            session.flush()
            session.add(GroupMember(group_id=group.id, user_id=user_id, slot=1))
            session.flush()
        return group
    except IntegrityError as error:
        if (
            isinstance(error.orig, UniqueViolation)
            and error.orig.diag.constraint_name == "uq_groups_request"
        ):
            previous = session.scalar(query)
            if previous is not None:
                return _same_group(previous, name)
        raise


def list_groups(session: Session, user_id: int, limit: int, offset: int) -> list[Group]:
    return list(
        session.scalars(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.created_at, Group.id)
            .limit(limit)
            .offset(offset)
        )
    )


def list_members(
    session: Session, group_id: int, limit: int, offset: int
) -> list[GroupMember]:
    return list(
        session.scalars(
            select(GroupMember)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.joined_at, GroupMember.user_id)
            .limit(limit)
            .offset(offset)
        )
    )


def issue_invite(
    session: Session, group_id: int, user_id: int, request_id: UUID
) -> tuple[GroupInvite, str | None]:
    with write_transaction(session):
        group = require_member(session, group_id, user_id, lock=True)
        require_owner(group, user_id)
        previous = session.scalar(
            select(GroupInvite).where(
                GroupInvite.group_id == group_id,
                GroupInvite.client_request_id == request_id,
            )
        )
        if previous is not None:
            return previous, None
        raw = new_secret()
        now = utc_now()
        invite = GroupInvite(
            group_id=group_id,
            client_request_id=request_id,
            token_hash=secret_digest(raw),
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        session.add(invite)
        session.flush()
    return invite, raw


def join_group(session: Session, user_id: int, token: str) -> Group:
    failure = ApiError(404, "invite_invalid", "Invitation is invalid or unavailable")
    digest = secret_digest(token)
    with write_transaction(session):
        # Lookup is deliberately non-locking; no group information leaves this service.
        group_id = session.scalar(
            select(GroupInvite.group_id).where(GroupInvite.token_hash == digest)
        )
        if group_id is None:
            raise failure
        group = session.scalar(
            select(Group).where(Group.id == group_id).with_for_update()
        )
        if group is None:
            raise failure
        invite = session.scalar(
            select(GroupInvite)
            .where(GroupInvite.token_hash == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utc_now()  # Check expiry after waiting for all locks, not before.
        if (
            invite is None
            or invite.consumed_at is not None
            or invite.revoked_at is not None
            or now >= invite.expires_at
        ):
            raise failure
        if session.get(GroupMember, (group.id, user_id)) is not None:
            raise ApiError(409, "already_member", "Already a member of this group")
        slots = set(
            session.scalars(
                select(GroupMember.slot).where(GroupMember.group_id == group.id)
            )
        )
        slot = next((slot for slot in range(1, 31) if slot not in slots), None)
        if slot is None:
            raise ApiError(409, "group_full", "Group already has 30 members")
        session.add(GroupMember(group_id=group.id, user_id=user_id, slot=slot))
        invite.consumed_at, invite.consumed_by = now, user_id
        session.flush()
    return group


def list_invites(
    session: Session, group_id: int, user_id: int, limit: int, offset: int
) -> list[GroupInvite]:
    group = require_member(session, group_id, user_id)
    require_owner(group, user_id)
    return list(
        session.scalars(
            select(GroupInvite)
            .where(GroupInvite.group_id == group_id)
            .order_by(GroupInvite.created_at, GroupInvite.id)
            .limit(limit)
            .offset(offset)
        )
    )


def revoke_invite(
    session: Session, group_id: int, user_id: int, invite_id: int
) -> GroupInvite:
    with write_transaction(session):
        group = require_member(session, group_id, user_id, lock=True)
        require_owner(group, user_id)
        invite = session.scalar(
            select(GroupInvite)
            .where(GroupInvite.id == invite_id, GroupInvite.group_id == group_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if invite is None:
            raise ApiError(
                404, "invite_invalid", "Invitation is invalid or unavailable"
            )
        if invite.consumed_at is not None:
            raise ApiError(
                409, "invite_consumed", "Invitation has already been consumed"
            )
        if invite.revoked_at is None:
            invite.revoked_at = utc_now()
        session.flush()
    return invite
