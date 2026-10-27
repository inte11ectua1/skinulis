from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import ApiError
from app.core.identity_tokens import new_secret, secret_digest
from app.core.security import create_access_token
from app.db import get_session
from app.main import create_app
from app.models import Group, GroupInvite, GroupMember, User
from app.schemas.groups import CapabilityInput, GroupCreate, LinkInput
from app.services import groups, telegram_identity

NOW = datetime(2026, 10, 27, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, postgres_password=SecretStr(new_secret()))


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def client(settings: Settings, session: MagicMock) -> Iterator[TestClient]:
    application = create_app(settings)
    application.dependency_overrides[get_session] = lambda: session
    with TestClient(application) as value:
        yield value


def group() -> Group:
    return Group(
        id=1, owner_id=1, name="Trip", created_at=NOW, client_request_id=uuid4()
    )


def invite() -> GroupInvite:
    return GroupInvite(
        id=1,
        group_id=1,
        client_request_id=uuid4(),
        token_hash=secret_digest(new_secret()),
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )


@pytest.mark.parametrize(
    "name,expected",
    [
        ("  Trip  ", "Trip"),
        ("е\u0308", "ё"),
        (" Поездка\u00a0", "Поездка"),
        ("a" * 120, "a" * 120),
    ],
)
def test_group_name_policy(name: str, expected: str) -> None:
    assert GroupCreate(name=name, client_request_id=uuid4()).name == expected


@pytest.mark.parametrize("name", ["", "  ", "a" * 121, "a\x00b", "a\nb", "a\u200bb"])
def test_invalid_names(name: str) -> None:
    with pytest.raises(ValidationError):
        GroupCreate(name=name, client_request_id=uuid4())


@pytest.mark.parametrize("field", ["user_id", "owner_id", "member_id", "telegram_id"])
def test_dto_forbids_actor_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        GroupCreate.model_validate(
            {"name": "Trip", "client_request_id": str(uuid4()), field: 123}
        )


@pytest.mark.parametrize("value", ["", "short", "!" * 43, "a" * 44, "é" * 43])
def test_secret_format_validation(value: str) -> None:
    with pytest.raises(ValidationError):
        CapabilityInput.model_validate({"token": value})
    with pytest.raises(ValidationError):
        LinkInput.model_validate({"code": value})


def test_capability_randomness_digest_and_repr() -> None:
    first, second = new_secret(), new_secret()
    assert first != second and len(first) == 43
    assert len(secret_digest(first)) == 64
    assert secret_digest(first) == secret_digest(first)
    assert first not in repr(CapabilityInput(token=SecretStr(first)))
    assert first not in repr(LinkInput(code=SecretStr(first)))


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({}, 401),
        ({"X-Bot-Service-Token": "bad"}, 401),
        ({"Authorization": "Bearer broken"}, 400),
    ],
)
def test_internal_auth_rejects_untrusted_before_db(
    client: TestClient, session: MagicMock, headers: dict[str, str], expected: int
) -> None:
    response = client.post("/internal/users/bootstrap", headers=headers, json={})
    assert response.status_code == expected
    assert set(response.json()["error"]) == {"code", "message", "request_id"}
    session.execute.assert_not_called()
    session.scalar.assert_not_called()


@pytest.mark.parametrize("actor", ["", "0", "-1", "01", "1.5", str(2**63), "abc"])
def test_internal_actor_validation(
    client: TestClient, settings: Settings, session: MagicMock, actor: str
) -> None:
    response = client.get(
        "/internal/users/me",
        headers={
            "X-Bot-Service-Token": settings.require_bot_service_token(),
            "X-Telegram-ID": actor,
        },
    )
    assert response.status_code == 400
    session.scalar.assert_not_called()


def test_internal_lookup_never_bootstraps(
    client: TestClient, settings: Settings, session: MagicMock
) -> None:
    headers = {
        "X-Bot-Service-Token": settings.require_bot_service_token(),
        "X-Telegram-ID": "123",
    }
    session.scalar.return_value = None
    response = client.get("/internal/users/me", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "telegram_profile_not_found"
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_public_actor_cannot_be_replaced(
    client: TestClient, settings: Settings, session: MagicMock
) -> None:
    token = create_access_token(1, settings.require_jwt_secret(), 15)
    response = client.get(
        "/groups", headers={"Authorization": "Bearer " + token, "X-Telegram-ID": "2"}
    )
    assert (
        response.status_code == 400
        and response.json()["error"]["code"] == "ambiguous_actor"
    )
    session.get.assert_not_called()
    assert (
        client.get(
            "/groups",
            headers={
                "X-Bot-Service-Token": settings.require_bot_service_token(),
                "X-Telegram-ID": "2",
            },
        ).status_code
        == 400
    )


def test_bootstrap_is_explicit_and_repeatable(session: MagicMock) -> None:
    existing = User(id=1, telegram_id=123)
    session.scalar.return_value = existing
    assert telegram_identity.bootstrap_user(session, 123) is existing
    session.add.assert_not_called()
    session.commit.assert_called_once()
    assert "pg_advisory_xact_lock" in str(session.execute.call_args.args[0])
    assert session.execute.call_args.args[1] == {"key": -123}


def test_bootstrap_creates_only_telegram_identity(session: MagicMock) -> None:
    session.scalar.return_value = None
    user = telegram_identity.bootstrap_user(session, 123)
    assert user.telegram_id == 123 and user.email is None and user.password_hash is None
    session.add.assert_called_once_with(user)


def test_create_group_adds_owner_and_commits_atomically(session: MagicMock) -> None:
    session.scalar.return_value = None

    def flush() -> None:
        record = session.add.call_args.args[0]
        if isinstance(record, Group):
            record.id = 42

    session.flush.side_effect = flush
    result = groups.create_group(session, 7, "Trip", uuid4())
    member = session.add.call_args_list[1].args[0]
    assert isinstance(member, GroupMember)
    assert (member.group_id, member.user_id, member.slot) == (42, 7, 1)
    assert result.owner_id == 7
    session.commit.assert_called_once()
    session.begin.assert_not_called()


def test_create_rollback_on_membership_failure(session: MagicMock) -> None:
    session.scalar.return_value = None
    session.flush.side_effect = [None, RuntimeError("membership failure")]
    with pytest.raises(RuntimeError):
        groups.create_group(session, 1, "Trip", uuid4())
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_group_replay_conflicting_body(session: MagicMock) -> None:
    previous = group()
    session.scalar.return_value = previous
    assert (
        groups.create_group(session, 1, "Trip", previous.client_request_id) is previous
    )
    with pytest.raises(ApiError) as caught:
        groups.create_group(session, 1, "Other", previous.client_request_id)
    assert caught.value.code == "request_conflict"


@pytest.mark.parametrize(
    "owner,member,status", [(1, True, 200), (2, True, 403), (1, False, 404)]
)
def test_owner_and_member_permissions(
    session: MagicMock, owner: int, member: bool, status: int
) -> None:
    value = group()
    value.owner_id = owner
    session.scalar.return_value = value
    session.get.return_value = (
        GroupMember(group_id=1, user_id=1, slot=1) if member else None
    )
    if status == 200:
        groups.require_owner(groups.require_member(session, 1, 1), 1)
    else:
        with pytest.raises(ApiError) as caught:
            groups.require_owner(groups.require_member(session, 1, 1), 1)
        assert caught.value.status == status


def test_invite_hash_ttl_and_replay(
    session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(groups, "utc_now", lambda: NOW)
    session.scalar.side_effect = [group(), None]
    session.get.return_value = GroupMember(group_id=1, user_id=1, slot=1)
    record, raw = groups.issue_invite(session, 1, 1, uuid4())
    assert raw is not None and record.token_hash == secret_digest(raw)
    assert record.expires_at - record.created_at == timedelta(hours=24)
    session.scalar.side_effect = [group(), record]
    repeated, raw = groups.issue_invite(session, 1, 1, record.client_request_id)
    assert repeated is record and raw is None


@pytest.mark.parametrize(
    "state", ["expired", "used", "revoked", "unknown", "member", "full"]
)
def test_join_rejects_invalid_and_conflicting_state(
    session: MagicMock, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    monkeypatch.setattr(groups, "utc_now", lambda: NOW)
    record = invite()
    if state == "expired":
        record.expires_at = NOW
    elif state == "used":
        record.consumed_at = NOW
    elif state == "revoked":
        record.revoked_at = NOW
    session.scalar.side_effect = [None] if state == "unknown" else [1, group(), record]
    session.get.return_value = (
        GroupMember(group_id=1, user_id=2, slot=2) if state == "member" else None
    )
    session.scalars.return_value = range(1, 31)
    with pytest.raises(ApiError) as caught:
        groups.join_group(session, 2, new_secret())
    assert caught.value.code == {"member": "already_member", "full": "group_full"}.get(
        state, "invite_invalid"
    )
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
    session.add.assert_not_called()


def test_join_consumes_once_under_group_lock(
    session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(groups, "utc_now", lambda: NOW)
    record = invite()
    session.scalar.side_effect = [1, group(), record]
    session.get.return_value = None
    session.scalars.return_value = [1]
    groups.join_group(session, 2, new_secret())
    assert record.consumed_by == 2 and record.consumed_at == NOW
    statements = [str(call.args[0]) for call in session.scalar.call_args_list]
    assert "FOR UPDATE" not in statements[0]
    assert "FROM groups" in statements[1] and "FOR UPDATE" in statements[1]
    assert "FROM group_invites" in statements[2] and "FOR UPDATE" in statements[2]
    assert session.add.call_args.args[0].slot == 2


def test_link_issuance_hash_and_ttl(
    session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram_identity, "utc_now", lambda: NOW)
    session.scalar.return_value = User(id=1, email="a@example.com")
    raw, code = telegram_identity.issue_link_code(session, 1)
    assert code.token_hash == secret_digest(raw)
    assert code.expires_at - code.created_at == timedelta(minutes=10)
    assert "UPDATE telegram_link_codes" in str(session.execute.call_args.args[0])


@pytest.mark.parametrize(
    "user,code",
    [
        (None, "invalid_token"),
        (User(id=1, telegram_id=1), "email_profile_required"),
        (User(id=1, email="a@example.com", telegram_id=1), "telegram_already_linked"),
    ],
)
def test_link_issuance_requires_unlinked_email(
    session: MagicMock, user: User | None, code: str
) -> None:
    session.scalar.return_value = user
    with pytest.raises(ApiError) as caught:
        telegram_identity.issue_link_code(session, 1)
    assert caught.value.code == code
    session.rollback.assert_called_once()


def test_service_secret_settings_isolation(settings: Settings) -> None:
    assert settings.require_bot_service_token() not in repr(settings)
    for value in [
        None,
        SecretStr(""),
        SecretStr("short"),
        settings.jwt_secret_key,
        settings.postgres_password,
    ]:
        changed = settings.model_copy(update={"bot_service_token": value})
        with pytest.raises(ValueError):
            changed.require_bot_service_token()


@pytest.mark.parametrize(
    "state",
    [
        "missing",
        "expired",
        "used",
        "revoked",
        "merge",
        "linked",
        "telegram_only",
        "valid",
    ],
)
def test_link_consumption_state_and_rollback(
    session: MagicMock, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    from app.models import TelegramLinkCode

    monkeypatch.setattr(telegram_identity, "utc_now", lambda: NOW)
    user = User(id=1, email="alice@example.com")
    code = TelegramLinkCode(
        id=1,
        user_id=1,
        token_hash=secret_digest(new_secret()),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    if state == "expired":
        code.expires_at = NOW
    elif state == "used":
        code.consumed_at = NOW
    elif state == "revoked":
        code.revoked_at = NOW
    elif state == "linked":
        user.telegram_id = 456
    elif state == "telegram_only":
        user.email = None
    session.scalar.side_effect = (
        [None]
        if state == "missing"
        else [1, user, code, 2 if state == "merge" else None]
    )
    if state == "valid":
        assert telegram_identity.link_telegram(session, 123, new_secret()) is user
        assert user.telegram_id == 123 and code.consumed_at == NOW
        session.commit.assert_called_once()
    else:
        with pytest.raises(ApiError) as caught:
            telegram_identity.link_telegram(session, 123, new_secret())
        assert caught.value.code == {
            "merge": "telegram_identity_conflict",
            "linked": "telegram_already_linked",
            "telegram_only": "email_profile_required",
        }.get(state, "link_code_invalid")
        session.rollback.assert_called_once()
        session.commit.assert_not_called()


def test_revoke_core_is_owner_only_repeatable_and_never_deletes(
    session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(groups, "utc_now", lambda: NOW)
    record = invite()
    session.scalar.side_effect = [group(), record, group(), record]
    session.get.return_value = GroupMember(group_id=1, user_id=1, slot=1)
    assert groups.revoke_invite(session, 1, 1, 1) is record
    assert groups.revoke_invite(session, 1, 1, 1).revoked_at == NOW
    session.delete.assert_not_called()
    session.scalar.side_effect = [group(), record]
    record.consumed_at = NOW
    with pytest.raises(ApiError) as caught:
        groups.revoke_invite(session, 1, 1, 1)
    assert caught.value.code == "invite_consumed"
