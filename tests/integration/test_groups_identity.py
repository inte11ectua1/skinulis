"""Real PostgreSQL identity, constraints and overlapping independent transactions."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from threading import Barrier
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.config import Settings
from app.core.errors import ApiError
from app.core.identity_tokens import new_secret, secret_digest, utc_now
from app.core.migrate import main as migrate
from app.core.security import create_access_token
from app.main import create_app
from app.models import Group, GroupInvite, GroupMember, TelegramLinkCode, User
from app.services import groups, telegram_identity

pytestmark = pytest.mark.integration


@dataclass
class Harness:
    client: TestClient
    engine: Engine
    sessions: sessionmaker[Session]
    settings: Settings

    def user(
        self, telegram_id: int | None = None, *, email: str | None = None
    ) -> tuple[int, dict[str, str]]:
        with self.sessions() as session, session.begin():
            user = User(
                telegram_id=telegram_id,
                email=email,
                password_hash="$argon2id$fixture-not-used-for-login" if email else None,
            )
            session.add(user)
            session.flush()
            user_id = user.id
        return user_id, {
            "Authorization": "Bearer "
            + create_access_token(user_id, self.settings.require_jwt_secret(), 15)
        }

    def service(self, telegram_id: int) -> dict[str, str]:
        return {
            "X-Bot-Service-Token": self.settings.require_bot_service_token(),
            "X-Telegram-ID": str(telegram_id),
        }

    def group(self, headers: dict[str, str], name: str = "Trip") -> int:
        response = self.client.post(
            "/groups",
            headers=headers,
            json={"name": name, "client_request_id": str(uuid4())},
        )
        assert response.status_code == 201
        value: int = response.json()["id"]
        return value

    def invite(self, group_id: int, headers: dict[str, str]) -> tuple[int, str]:
        response = self.client.post(
            f"/groups/{group_id}/invites",
            headers=headers,
            json={"client_request_id": str(uuid4())},
        )
        assert response.status_code == 201
        body = response.json()
        return body["id"], body["token"]


def error(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.fixture
def h(database_url: URL) -> Iterator[Harness]:
    assert migrate() == 0
    engine = create_engine(database_url, hide_parameters=True)
    settings = Settings(_env_file=None)
    try:
        with TestClient(create_app(settings)) as client:
            yield Harness(
                client, engine, sessionmaker(engine, expire_on_commit=False), settings
            )
    finally:
        engine.dispose()


def test_t05_upgrade_preserves_users_and_one_head(database_url: URL) -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "0002_users")
    engine = create_engine(database_url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            uid = connection.execute(
                text("INSERT INTO users (telegram_id) VALUES (123) RETURNING id")
            ).scalar_one()
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert ScriptDirectory.from_config(config).get_heads() == [
            "0004_financial_domain"
        ]
        command.check(config)
        with Session(engine) as session:
            assert session.get(User, uid) is not None
        schema = inspect(engine)
        assert schema.get_pk_constraint("group_members")["constrained_columns"] == [
            "group_id",
            "user_id",
        ]
        owner_fk = next(
            fk
            for fk in schema.get_foreign_keys("groups")
            if fk["name"] == "fk_groups_owner_membership"
        )
        assert owner_fk["options"] == {"deferrable": True, "initially": "DEFERRED"}
        assert schema.get_indexes("group_members")[0]["name"]
    finally:
        engine.dispose()


def test_group_creation_replay_access_pagination(h: Harness) -> None:
    uid, owner = h.user(100)
    _, outsider = h.user(200)
    key = str(uuid4())
    payload = {"name": "  Поездка  ", "client_request_id": key}
    created = h.client.post("/groups", headers=owner, json=payload)
    assert created.status_code == 201 and created.json()["name"] == "Поездка"
    gid = created.json()["id"]
    assert created.json()["owner_id"] == uid
    assert (
        h.client.post("/groups", headers=owner, json=payload).json() == created.json()
    )
    error(
        h.client.post("/groups", headers=owner, json={**payload, "name": "Different"}),
        409,
        "request_conflict",
    )
    for path in (f"/groups/{gid}", f"/groups/{gid}/members"):
        error(h.client.get(path, headers=outsider), 404, "group_not_found")
        assert h.client.get(path, headers=owner).status_code == 200
    members = h.client.get(f"/groups/{gid}/members", headers=owner).json()
    assert set(members) == {"items", "limit", "offset"}
    assert members["limit"] == 20 and members["offset"] == 0
    assert members["items"][0]["user_id"] == uid and members["items"][0]["is_owner"]
    assert set(members["items"][0]) == {"user_id", "joined_at", "is_owner"}
    second = h.group(owner, "Another")
    page = h.client.get("/groups?limit=1&offset=1", headers=owner).json()
    assert [g["id"] for g in page["items"]] == [second]
    assert h.client.get("/groups", headers=outsider).json()["items"] == []
    for query in ("limit=0", "limit=101", "offset=-1"):
        error(h.client.get("/groups?" + query, headers=owner), 400, "validation_error")
    error(
        h.client.post("/groups", headers=owner, json={**payload, "owner_id": 999}),
        400,
        "validation_error",
    )
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Group)) == 2
        membership = session.get(GroupMember, (gid, uid))
        assert membership is not None and membership.slot == 1


def test_group_and_membership_rollback_on_database_failure(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, _ = h.user(100)
    with h.sessions() as session:
        original = session.flush

        def broken_flush(*args: object, **kwargs: object) -> None:
            if any(isinstance(record, GroupMember) for record in session.new):
                raise RuntimeError("simulated membership write failure")
            original()

        monkeypatch.setattr(session, "flush", broken_flush)
        with pytest.raises(RuntimeError):
            groups.create_group(session, uid, "Trip", uuid4())
        monkeypatch.setattr(session, "flush", original)
        assert session.scalar(select(func.count()).select_from(Group)) == 0
        assert session.scalar(select(func.count()).select_from(GroupMember)) == 0
        groups.create_group(session, uid, "After rollback", uuid4())


def test_invite_hash_single_use_permissions_and_replay(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    _, owner = h.user(100)
    member_id, member = h.user(200)
    _, outsider = h.user(300)
    gid = h.group(owner)
    key = str(uuid4())
    issued = h.client.post(
        f"/groups/{gid}/invites", headers=owner, json={"client_request_id": key}
    )
    token = issued.json()["token"]
    assert issued.status_code == 201 and issued.headers["Cache-Control"] == "no-store"
    replay = h.client.post(
        f"/groups/{gid}/invites", headers=owner, json={"client_request_id": key}
    )
    assert replay.json()["token"] is None and replay.json()["id"] == issued.json()["id"]
    error(
        h.client.post(
            f"/groups/{gid}/invites",
            headers=outsider,
            json={"client_request_id": str(uuid4())},
        ),
        404,
        "group_not_found",
    )
    error(
        h.client.post("/group-invites/join", headers=owner, json={"token": token}),
        409,
        "already_member",
    )
    joined = h.client.post("/group-invites/join", headers=member, json={"token": token})
    assert joined.status_code == 200 and joined.json()["id"] == gid
    error(
        h.client.post("/group-invites/join", headers=outsider, json={"token": token}),
        404,
        "invite_invalid",
    )
    error(
        h.client.post("/group-invites/join", headers=member, json={"token": token}),
        404,
        "invite_invalid",
    )
    error(
        h.client.post(
            f"/groups/{gid}/invites",
            headers=member,
            json={"client_request_id": str(uuid4())},
        ),
        403,
        "owner_required",
    )
    members = h.client.get(f"/groups/{gid}/members", headers=member).json()["items"]
    assert len(members) == 2 and not members[1]["is_owner"]
    with h.sessions() as session:
        stored = session.get(GroupInvite, issued.json()["id"])
        assert stored is not None and stored.token_hash == secret_digest(token)
        assert stored.expires_at - stored.created_at == timedelta(hours=24)
        assert stored.consumed_by == member_id and stored.consumed_at is not None
    assert token not in caplog.text


@pytest.mark.parametrize("kind", ["expired", "revoked", "unknown"])
def test_unusable_invites_are_indistinguishable(
    h: Harness, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, owner = h.user(100)
    _, member = h.user(200)
    gid = h.group(owner)
    iid, token = h.invite(gid, owner)
    with h.sessions() as session, session.begin():
        record = session.get(GroupInvite, iid)
        assert record is not None
        if kind == "expired":
            monkeypatch.setattr(groups, "utc_now", lambda: record.expires_at)
        elif kind == "revoked":
            record.revoked_at = utc_now()
        else:
            token = new_secret()
    error(
        h.client.post("/group-invites/join", headers=member, json={"token": token}),
        404,
        "invite_invalid",
    )
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(GroupMember)) == 1


def overlap(
    h: Harness, lock_sql: str, params: dict[str, int], actions: list[Callable[[], str]]
) -> list[str]:
    """Hold a real conflicting lock until both independent worker transactions wait.

    pg_stat_activity proves overlap at the lock, beyond a start-only thread barrier.
    Polls have a bounded deadline; no TTL is tested by waiting in real time.
    """
    barrier = Barrier(len(actions) + 1)

    def run(action: Callable[[], str]) -> str:
        barrier.wait(timeout=10)
        return action()

    with (
        ThreadPoolExecutor(max_workers=len(actions)) as pool,
        h.engine.connect() as blocker,
    ):
        transaction = blocker.begin()
        blocker.execute(text(lock_sql), params)
        futures = [pool.submit(run, action) for action in actions]
        barrier.wait(timeout=10)
        try:
            deadline = monotonic() + 10
            while True:
                with h.engine.connect() as observer:
                    waiting = observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid() AND wait_event_type='Lock'"
                        )
                    )
                if waiting is not None and waiting >= len(actions):
                    break
                assert monotonic() < deadline, (
                    "Workers did not overlap while waiting for database locks"
                )
                sleep(0.01)
        finally:
            transaction.rollback()
        return [f.result(timeout=15) for f in futures]


def join_action(h: Harness, uid: int, token: str) -> Callable[[], str]:
    def run() -> str:
        with h.sessions() as session:
            try:
                groups.join_group(session, uid, token)
                return "joined"
            except ApiError as failure:
                return failure.code

    return run


def test_concurrent_join_same_invite_exactly_one_winner(h: Harness) -> None:
    _, owner = h.user(100)
    first, _ = h.user(200)
    second, _ = h.user(300)
    gid = h.group(owner)
    _, token = h.invite(gid, owner)
    results = overlap(
        h,
        "SELECT id FROM groups WHERE id=:id FOR UPDATE",
        {"id": gid},
        [join_action(h, uid, token) for uid in (first, second)],
    )
    assert sorted(results) == ["invite_invalid", "joined"]
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(GroupMember)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(GroupInvite)
                .where(GroupInvite.consumed_at.is_not(None))
            )
            == 1
        )


def test_concurrent_join_last_slot_never_exceeds_thirty(h: Harness) -> None:
    _, owner = h.user(100)
    gid = h.group(owner)
    with h.sessions() as session, session.begin():
        for slot in range(2, 30):
            user = User(telegram_id=1000 + slot)
            session.add(user)
            session.flush()
            session.add(GroupMember(group_id=gid, user_id=user.id, slot=slot))
    first, _ = h.user(200)
    second, _ = h.user(300)
    invites = [h.invite(gid, owner)[1] for _ in range(2)]
    results = overlap(
        h,
        "SELECT id FROM groups WHERE id=:id FOR UPDATE",
        {"id": gid},
        [
            join_action(h, uid, token)
            for uid, token in zip((first, second), invites, strict=True)
        ],
    )
    assert sorted(results) == ["group_full", "joined"]
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(GroupMember)) == 30
        assert (
            session.scalar(
                select(func.count())
                .select_from(GroupInvite)
                .where(GroupInvite.consumed_at.is_(None))
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(GroupInvite)
                .where(GroupInvite.consumed_at.is_not(None))
            )
            == 1
        )


def test_concurrent_bootstrap_returns_one_user(h: Harness) -> None:
    def action() -> str:
        with h.sessions() as session:
            return str(telegram_identity.bootstrap_user(session, 123).id)

    results = overlap(
        h,
        "SELECT pg_advisory_xact_lock(CAST(:id AS BIGINT))",
        {"id": -123},
        [action, action],
    )
    assert results[0] == results[1]
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1


def test_service_onboarding_link_and_jwt_regression(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    service = h.service(123)
    error(
        h.client.get("/internal/users/me", headers=service),
        404,
        "telegram_profile_not_found",
    )
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0
    password = new_secret()
    registered = h.client.post(
        "/auth/register", json={"email": "alice@example.com", "password": password}
    )
    assert registered.status_code == 201
    login = h.client.post(
        "/auth/login", json={"email": "alice@example.com", "password": password}
    )
    assert login.status_code == 200
    jwt_token = login.json()["access_token"]
    auth = {"Authorization": "Bearer " + jwt_token}
    issued = h.client.post("/users/me/telegram-link-code", headers=auth, json={})
    assert issued.status_code == 201
    code = issued.json()["code"]
    error(
        h.client.post(
            "/internal/users/telegram-link",
            headers={**service, **auth},
            json={"code": code},
        ),
        400,
        "ambiguous_actor",
    )
    error(
        h.client.post(
            "/internal/users/telegram-link", headers=auth, json={"code": code}
        ),
        400,
        "ambiguous_actor",
    )
    linked = h.client.post(
        "/internal/users/telegram-link", headers=service, json={"code": code}
    )
    assert linked.status_code == 200 and linked.json()["id"] == registered.json()["id"]
    assert linked.json()["telegram_id"] == 123
    assert h.client.get("/internal/users/me", headers=service).json() == linked.json()
    assert h.client.get("/users/me", headers=auth).json() == linked.json()
    assert (
        h.client.post("/internal/users/bootstrap", headers=service, json={}).json()
        == linked.json()
    )
    error(
        h.client.post(
            "/internal/users/telegram-link", headers=service, json={"code": code}
        ),
        404,
        "link_code_invalid",
    )
    error(
        h.client.post("/users/me/telegram-link-code", headers=auth, json={}),
        409,
        "telegram_already_linked",
    )
    error(h.client.post("/users/me/telegram-link-code", json={}), 401, "invalid_token")
    new_actor = h.service(456)
    created = h.client.post("/internal/users/bootstrap", headers=new_actor, json={})
    assert created.status_code == 200 and created.json()["email"] is None
    assert created.json()["id"] != linked.json()["id"]
    assert (
        h.client.post("/internal/users/bootstrap", headers=new_actor, json={}).json()
        == created.json()
    )
    error(
        h.client.post(
            "/internal/users/bootstrap", headers=new_actor, json={"telegram_id": 999}
        ),
        400,
        "validation_error",
    )
    error(
        h.client.get(
            "/internal/users/me",
            headers={"X-Bot-Service-Token": new_secret(), "X-Telegram-ID": "123"},
        ),
        401,
        "invalid_service_token",
    )
    error(h.client.get("/groups", headers=service), 400, "ambiguous_actor")
    created_group = h.client.post(
        "/internal/groups",
        headers=new_actor,
        json={"name": "Bot trip", "client_request_id": str(uuid4())},
    )
    assert created_group.status_code == 201
    gid = created_group.json()["id"]
    assert (
        h.client.get(f"/internal/groups/{gid}/members", headers=new_actor).status_code
        == 200
    )
    error(
        h.client.get(f"/internal/groups/{gid}", headers=service), 404, "group_not_found"
    )
    for secret in [password, jwt_token, code, service["X-Bot-Service-Token"]]:
        assert secret not in caplog.text
    with h.sessions() as session:
        record = session.scalar(select(TelegramLinkCode))
        assert record is not None and record.token_hash == secret_digest(code)
        assert record.expires_at - record.created_at == timedelta(minutes=10)
        user = session.get(User, created.json()["id"])
        assert user is not None and user.email is None and user.password_hash is None


@pytest.mark.parametrize("kind", ["unknown", "expired", "replaced", "merge"])
def test_link_invalid_state_keeps_accounts_intact(
    h: Harness, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, auth = h.user(email="alice@example.com")
    issued = h.client.post("/users/me/telegram-link-code", headers=auth, json={})
    code = issued.json()["code"]
    if kind == "unknown":
        code = new_secret()
    elif kind == "expired":
        with h.sessions() as session:
            record = session.scalar(select(TelegramLinkCode))
            assert record is not None
            monkeypatch.setattr(telegram_identity, "utc_now", lambda: record.expires_at)
    elif kind == "replaced":
        assert (
            h.client.post(
                "/users/me/telegram-link-code", headers=auth, json={}
            ).status_code
            == 201
        )
    else:
        h.user(123)
    response = h.client.post(
        "/internal/users/telegram-link", headers=h.service(123), json={"code": code}
    )
    error(
        response,
        409 if kind == "merge" else 404,
        "telegram_identity_conflict" if kind == "merge" else "link_code_invalid",
    )
    with h.sessions() as session:
        user = session.get(User, uid)
        assert user is not None and user.telegram_id is None
        record = session.scalar(
            select(TelegramLinkCode).where(
                TelegramLinkCode.token_hash == secret_digest(code)
            )
        )
        if record is not None:
            assert record.consumed_at is None


def test_concurrent_link_one_code_cannot_attach_two_actors(h: Harness) -> None:
    uid, _ = h.user(email="alice@example.com")
    with h.sessions() as session:
        code, _ = telegram_identity.issue_link_code(session, uid)

    def action(tid: int) -> Callable[[], str]:
        def run() -> str:
            with h.sessions() as session:
                try:
                    telegram_identity.link_telegram(session, tid, code)
                    return "linked"
                except ApiError as failure:
                    return failure.code

        return run

    results = overlap(
        h,
        "SELECT id FROM users WHERE id=:id FOR UPDATE",
        {"id": uid},
        [action(123), action(456)],
    )
    assert sorted(results) == ["link_code_invalid", "linked"]
    with h.sessions() as session:
        user = session.get(User, uid)
        assert user is not None and user.telegram_id in {123, 456}
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(TelegramLinkCode)
                .where(TelegramLinkCode.consumed_at.is_not(None))
            )
            == 1
        )


def test_concurrent_bootstrap_and_link_never_merge(h: Harness) -> None:
    uid, _ = h.user(email="alice@example.com")
    with h.sessions() as session:
        raw, _ = telegram_identity.issue_link_code(session, uid)

    def bootstrap() -> str:
        with h.sessions() as session:
            return "bootstrap:" + str(telegram_identity.bootstrap_user(session, 123).id)

    def link() -> str:
        with h.sessions() as session:
            try:
                telegram_identity.link_telegram(session, 123, raw)
                return "linked"
            except ApiError as failure:
                return failure.code

    results = overlap(
        h,
        "SELECT pg_advisory_xact_lock(CAST(:id AS BIGINT))",
        {"id": -123},
        [bootstrap, link],
    )
    with h.sessions() as session:
        all_users = list(session.scalars(select(User).order_by(User.id)))
        assert sum(user.telegram_id == 123 for user in all_users) == 1
        if "linked" in results:
            assert len(all_users) == 1 and all_users[0].id == uid
        else:
            assert "telegram_identity_conflict" in results and len(all_users) == 2
            assert all_users[0].telegram_id is None


def test_schema_rejects_owner_without_membership_and_history_deletion(
    h: Harness,
) -> None:
    uid, owner = h.user(100)
    with h.sessions() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    Group(owner_id=uid, name="Orphan", client_request_id=uuid4())
                )
                session.flush()  # Deferred owner FK is checked at commit.
        assert session.scalar(select(func.count()).select_from(Group)) == 0
    gid = h.group(owner)
    for sql in (
        "DELETE FROM group_members WHERE group_id=:gid",
        "DELETE FROM groups WHERE id=:gid",
        "DELETE FROM users WHERE id=:uid",
    ):
        with pytest.raises(IntegrityError), h.engine.begin() as connection:
            connection.execute(text(sql), {"gid": gid, "uid": uid})
    with h.sessions() as session:
        assert session.get(GroupMember, (gid, uid)) is not None


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_member",
        "duplicate_slot",
        "slot_zero",
        "slot_31",
        "unknown_group",
        "unknown_user",
        "empty_name",
        "long_name",
        "bad_hash",
        "bad_ttl",
        "consumed_without_actor",
        "link_bad_hash",
        "link_bad_ttl",
    ],
)
def test_database_constraints_and_recovery(h: Harness, case: str) -> None:
    uid, owner = h.user(100)
    other, _ = h.user(200)
    gid = h.group(owner)
    now = utc_now()
    with h.sessions() as session:
        with (
            pytest.raises(DataError if case == "long_name" else IntegrityError),
            session.begin(),
        ):
            if case in {"empty_name", "long_name"}:
                session.execute(
                    text("UPDATE groups SET name=:name WHERE id=:id"),
                    {"name": "" if case == "empty_name" else "x" * 121, "id": gid},
                )
            elif case.startswith("link_"):
                session.add(
                    TelegramLinkCode(
                        user_id=uid,
                        token_hash="invalid"
                        if case == "link_bad_hash"
                        else secret_digest(new_secret()),
                        created_at=now,
                        expires_at=now
                        + timedelta(minutes=9 if case == "link_bad_ttl" else 10),
                    )
                )
            elif case in {"bad_hash", "bad_ttl", "consumed_without_actor"}:
                session.add(
                    GroupInvite(
                        group_id=gid,
                        client_request_id=uuid4(),
                        token_hash="invalid"
                        if case == "bad_hash"
                        else secret_digest(new_secret()),
                        created_at=now,
                        expires_at=now
                        + timedelta(hours=23 if case == "bad_ttl" else 24),
                        consumed_at=now if case == "consumed_without_actor" else None,
                    )
                )
            else:
                session.add(
                    GroupMember(
                        group_id=999999 if case == "unknown_group" else gid,
                        user_id=uid
                        if case == "duplicate_member"
                        else 999999
                        if case == "unknown_user"
                        else other,
                        slot={"duplicate_slot": 1, "slot_zero": 0, "slot_31": 31}.get(
                            case, 2
                        ),
                    )
                )
            session.flush()
        with session.begin():
            assert session.get(Group, gid) is not None


def test_concurrent_group_creation_replays_one_atomic_result(h: Harness) -> None:
    uid, _ = h.user(100)
    request_id = uuid4()

    def action() -> str:
        with h.sessions() as session:
            return str(groups.create_group(session, uid, "Trip", request_id).id)

    results = overlap(
        h, "SELECT id FROM users WHERE id=:id FOR UPDATE", {"id": uid}, [action, action]
    )
    assert results[0] == results[1]
    with h.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Group)) == 1
        assert session.scalar(select(func.count()).select_from(GroupMember)) == 1


def test_link_code_is_issued_only_for_jwt_actor_and_no_public_consumer(
    h: Harness,
) -> None:
    first, auth1 = h.user(email="alice@example.com")
    second, auth2 = h.user(email="bob@example.com")
    error(
        h.client.post(
            "/users/me/telegram-link-code", headers=auth2, json={"user_id": first}
        ),
        400,
        "validation_error",
    )
    issued = h.client.post(
        f"/users/me/telegram-link-code?user_id={first}", headers=auth2, json={}
    )
    code = issued.json()["code"]
    error(
        h.client.post(
            "/internal/users/telegram-link", headers=auth1, json={"code": code}
        ),
        400,
        "ambiguous_actor",
    )
    linked = h.client.post(
        "/internal/users/telegram-link", headers=h.service(123), json={"code": code}
    )
    assert linked.status_code == 200 and linked.json()["id"] == second
    with h.sessions() as session:
        user = session.get(User, first)
        assert user is not None and user.telegram_id is None


def test_internal_group_operations_apply_same_membership_and_invite_rules(
    h: Harness,
) -> None:
    _, owner = h.user(100)
    h.user(200)
    h.user(300)
    gid = h.group(owner)
    iid, raw = h.invite(gid, owner)
    actor = h.service(200)
    error(
        h.client.get(f"/internal/groups/{gid}", headers=actor), 404, "group_not_found"
    )
    joined = h.client.post(
        "/internal/group-invites/join", headers=actor, json={"token": raw}
    )
    assert joined.status_code == 200 and joined.json()["id"] == gid
    assert (
        h.client.get("/internal/groups", headers=actor).json()["items"][0]["id"] == gid
    )
    error(
        h.client.post(
            f"/internal/groups/{gid}/invites",
            headers=actor,
            json={"client_request_id": str(uuid4())},
        ),
        403,
        "owner_required",
    )
    error(
        h.client.post(
            "/internal/group-invites/join",
            headers=h.service(300),
            json={"token": raw, "user_id": 200},
        ),
        400,
        "validation_error",
    )
    with h.sessions() as session:
        stored = session.get(GroupInvite, iid)
        assert stored is not None and stored.consumed_by is not None


def test_owner_change_to_non_member_and_hash_reuse_are_rejected(h: Harness) -> None:
    uid, owner = h.user(100)
    other, _ = h.user(200)
    gid = h.group(owner)
    iid, raw = h.invite(gid, owner)
    with pytest.raises(IntegrityError), h.engine.begin() as connection:
        connection.execute(
            text("UPDATE groups SET owner_id=:uid WHERE id=:gid"),
            {"uid": other, "gid": gid},
        )
    now = utc_now()
    with pytest.raises(IntegrityError), h.sessions() as session, session.begin():
        session.add(
            GroupInvite(
                group_id=gid,
                client_request_id=uuid4(),
                token_hash=secret_digest(raw),
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
    with h.sessions() as session:
        group = session.get(Group, gid)
        assert group is not None and group.owner_id == uid
        assert session.get(GroupInvite, iid) is not None


def test_consumed_invite_requires_membership_in_its_group(h: Harness) -> None:
    _, owner = h.user(100)
    stranger, _ = h.user(200)
    gid = h.group(owner)
    iid, _ = h.invite(gid, owner)
    with pytest.raises(IntegrityError), h.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE group_invites SET consumed_by=:uid, consumed_at=created_at WHERE id=:iid"
            ),
            {"uid": stranger, "iid": iid},
        )
    with h.sessions() as session:
        invite = session.get(GroupInvite, iid)
        assert (
            invite is not None
            and invite.consumed_at is None
            and invite.consumed_by is None
        )


def test_invite_management_core_owner_checks_pagination_and_revoke(h: Harness) -> None:
    uid, owner = h.user(100)
    other, _ = h.user(200)
    gid = h.group(owner)
    iid, raw = h.invite(gid, owner)
    second, _ = h.invite(gid, owner)
    with h.sessions() as session:
        assert [i.id for i in groups.list_invites(session, gid, uid, 1, 1)] == [second]
        with pytest.raises(ApiError) as caught:
            groups.list_invites(session, gid, other, 20, 0)
        assert caught.value.code == "group_not_found"
        first = groups.revoke_invite(session, gid, uid, iid)
        revoked_at = first.revoked_at
        assert revoked_at is not None
        assert groups.revoke_invite(session, gid, uid, iid).revoked_at == revoked_at
        assert session.get(GroupInvite, iid) is not None
    with h.sessions() as session, pytest.raises(ApiError) as caught:
        groups.join_group(session, other, raw)
    assert caught.value.code == "invite_invalid"


def test_concurrent_revoke_and_join_have_one_serialized_outcome(h: Harness) -> None:
    uid, owner = h.user(100)
    member, _ = h.user(200)
    gid = h.group(owner)
    iid, raw = h.invite(gid, owner)

    def revoke() -> str:
        with h.sessions() as session:
            try:
                groups.revoke_invite(session, gid, uid, iid)
                return "revoked"
            except ApiError as failure:
                return failure.code

    results = overlap(
        h,
        "SELECT id FROM groups WHERE id=:id FOR UPDATE",
        {"id": gid},
        [revoke, join_action(h, member, raw)],
    )
    assert sorted(results) in [
        ["invite_invalid", "revoked"],
        ["invite_consumed", "joined"],
    ]
    with h.sessions() as session:
        record = session.get(GroupInvite, iid)
        assert record is not None
        if "joined" in results:
            assert record.consumed_at is not None and record.revoked_at is None
            assert session.get(GroupMember, (gid, member)) is not None
        else:
            assert record.consumed_at is None and record.revoked_at is not None
            assert session.get(GroupMember, (gid, member)) is None


@pytest.mark.parametrize("internal", [False, True])
def test_http_invite_list_contains_all_states_with_stable_pagination(
    h: Harness, internal: bool
) -> None:
    _, owner = h.user(100)
    _, member = h.user(200)
    gid = h.group(owner)
    prefix = "/internal" if internal else ""
    headers = h.service(100) if internal else owner
    path = prefix + f"/groups/{gid}/invites"
    empty = h.client.get(path, headers=headers)
    assert empty.status_code == 200 and empty.json() == {
        "items": [],
        "limit": 20,
        "offset": 0,
    }
    issued = [h.invite(gid, owner) for _ in range(4)]
    active, expired, consumed, revoked = [item[0] for item in issued]
    assert (
        h.client.post(
            "/group-invites/join", headers=member, json={"token": issued[2][1]}
        ).status_code
        == 200
    )
    assert h.client.delete(path + f"/{revoked}", headers=headers).status_code == 200
    now = utc_now()
    with h.sessions() as session, session.begin():
        for iid, _ in issued:
            record = session.get(GroupInvite, iid)
            assert record is not None
            record.created_at = now - (
                timedelta(days=2) if iid == expired else timedelta(minutes=10)
            )
            record.expires_at = record.created_at + timedelta(hours=24)
    response = h.client.get(path, headers=headers)
    assert (
        response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    )
    body = response.json()
    assert set(body) == {"items", "limit", "offset"}
    assert [item["id"] for item in body["items"]] == [
        expired,
        active,
        consumed,
        revoked,
    ]
    fields = {
        "id",
        "group_id",
        "client_request_id",
        "created_at",
        "expires_at",
        "consumed_at",
        "revoked_at",
    }
    for item in body["items"]:
        assert set(item) == fields
    for _, raw in issued:
        assert raw not in response.text
    with h.sessions() as session:
        for stored in session.scalars(select(GroupInvite)):
            assert stored.token_hash not in response.text
    assert body["items"][2]["consumed_at"] is not None
    assert body["items"][3]["revoked_at"] is not None
    page = h.client.get(path + "?limit=2&offset=1", headers=headers).json()
    assert [item["id"] for item in page["items"]] == [active, consumed]
    assert page["limit"] == 2 and page["offset"] == 1
    assert h.client.get(path + "?offset=4", headers=headers).json()["items"] == []
    for query in ("limit=0", "limit=101", "offset=-1"):
        error(
            h.client.get(path + "?" + query, headers=headers), 400, "validation_error"
        )


@pytest.mark.parametrize("internal", [False, True])
def test_http_revoke_permissions_hidden_objects_and_repeat(
    h: Harness, internal: bool
) -> None:
    uid, owner = h.user(100)
    member_id, member = h.user(200)
    _, stranger = h.user(300)
    gid = h.group(owner)
    _, membership_invite = h.invite(gid, owner)
    assert (
        h.client.post(
            "/group-invites/join", headers=member, json={"token": membership_invite}
        ).status_code
        == 200
    )
    iid, raw = h.invite(gid, owner)
    prefix = "/internal" if internal else ""
    auth = h.service(100) if internal else owner
    member_auth = h.service(200) if internal else member
    stranger_auth = h.service(300) if internal else stranger
    path = prefix + f"/groups/{gid}/invites"
    for method, suffix in (("GET", ""), ("DELETE", f"/{iid}")):
        error(
            h.client.request(method, path + suffix, headers=member_auth),
            403,
            "owner_required",
        )
        error(
            h.client.request(method, path + suffix, headers=stranger_auth),
            404,
            "group_not_found",
        )
        error(
            h.client.request(
                method, prefix + "/groups/999999/invites" + suffix, headers=auth
            ),
            404,
            "group_not_found",
        )
    # A JSON/query actor ID is never authority, even on a bodyless DELETE.
    error(
        h.client.request(
            "DELETE",
            path + f"/{iid}?user_id={uid}",
            headers=member_auth,
            json={"owner_id": uid, "user_id": uid},
        ),
        403,
        "owner_required",
    )
    other_gid = h.group(owner, "Other group")
    other_iid, _ = h.invite(other_gid, owner)
    error(h.client.delete(path + f"/{other_iid}", headers=auth), 404, "invite_invalid")
    error(h.client.delete(path + "/999999", headers=auth), 404, "invite_invalid")
    first = h.client.delete(path + f"/{iid}", headers=auth)
    second = h.client.delete(path + f"/{iid}", headers=auth)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() and first.json()["revoked_at"] is not None
    assert first.headers["Cache-Control"] == "no-store"
    assert set(first.json()) == {
        "id",
        "group_id",
        "client_request_id",
        "created_at",
        "expires_at",
        "consumed_at",
        "revoked_at",
    }
    assert raw not in first.text
    error(
        h.client.post("/group-invites/join", headers=stranger, json={"token": raw}),
        404,
        "invite_invalid",
    )
    with h.sessions() as session:
        stored = session.get(GroupInvite, iid)
        assert (
            stored is not None
            and stored.revoked_at is not None
            and stored.consumed_at is None
        )
        assert stored.token_hash not in first.text
        assert session.get(GroupMember, (gid, member_id)) is not None


@pytest.mark.parametrize("internal", [False, True])
def test_http_revoke_consumed_conflicts_and_expired_can_be_revoked(
    h: Harness, internal: bool
) -> None:
    _, owner = h.user(100)
    _, member = h.user(200)
    gid = h.group(owner)
    used, token = h.invite(gid, owner)
    expired, _ = h.invite(gid, owner)
    assert (
        h.client.post(
            "/group-invites/join", headers=member, json={"token": token}
        ).status_code
        == 200
    )
    now = utc_now()
    with h.sessions() as session, session.begin():
        record = session.get(GroupInvite, expired)
        assert record is not None
        record.created_at = now - timedelta(days=2)
        record.expires_at = record.created_at + timedelta(hours=24)
    prefix = "/internal" if internal else ""
    auth = h.service(100) if internal else owner
    path = prefix + f"/groups/{gid}/invites"
    before = h.client.get(path, headers=auth).json()
    error(h.client.delete(path + f"/{used}", headers=auth), 409, "invite_consumed")
    assert h.client.get(path, headers=auth).json() == before
    response = h.client.delete(path + f"/{expired}", headers=auth)
    assert response.status_code == 200 and response.json()["revoked_at"] is not None
    assert response.json()["expires_at"] < response.json()["revoked_at"]
    assert h.client.delete(path + f"/{expired}", headers=auth).json() == response.json()


@pytest.mark.parametrize("internal", [False, True])
def test_http_revoke_racing_join_has_exactly_one_effect(
    h: Harness, internal: bool
) -> None:
    _, owner = h.user(100)
    member_id, member = h.user(200)
    gid = h.group(owner)
    iid, raw = h.invite(gid, owner)
    prefix = "/internal" if internal else ""
    auth = h.service(100) if internal else owner
    member_auth = h.service(200) if internal else member

    def revoke() -> str:
        response = h.client.delete(
            prefix + f"/groups/{gid}/invites/{iid}", headers=auth
        )
        return (
            "revoked"
            if response.status_code == 200
            else str(response.json()["error"]["code"])
        )

    def join() -> str:
        response = h.client.post(
            prefix + "/group-invites/join", headers=member_auth, json={"token": raw}
        )
        return (
            "joined"
            if response.status_code == 200
            else str(response.json()["error"]["code"])
        )

    results = overlap(
        h, "SELECT id FROM groups WHERE id=:id FOR UPDATE", {"id": gid}, [revoke, join]
    )
    assert sorted(results) in [
        ["invite_invalid", "revoked"],
        ["invite_consumed", "joined"],
    ]
    with h.sessions() as session:
        record = session.get(GroupInvite, iid)
        assert record is not None
        assert (record.revoked_at is not None, record.consumed_at is not None) == (
            "revoked" in results,
            "joined" in results,
        )
        assert (session.get(GroupMember, (gid, member_id)) is not None) == (
            "joined" in results
        )
