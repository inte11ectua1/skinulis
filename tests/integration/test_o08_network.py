"""Actual TCP response loss after committed creates; no ASGI/TestClient shortcut."""

import os
import socket
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Expense, Group, GroupMember, Settlement, User
from scripts.o08_support import LocalAPI, disposable_database, local_api

pytestmark = pytest.mark.integration


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[LocalAPI, URL, int]]:
    with disposable_database(os.environ["TEST_DATABASE_URL"]) as url:
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        from app.core.migrate import main as migrate

        assert migrate() == 0
        engine = create_engine(url, hide_parameters=True)
        try:
            with Session(engine) as session, session.begin():
                session.add_all(
                    User(id=i, telegram_id=1000000 + i) for i in (10, 20, 30)
                )
                session.flush()
                group = Group(
                    owner_id=10, name="O08 network", client_request_id=uuid4()
                )
                session.add(group)
                session.flush()
                session.add_all(
                    GroupMember(group_id=group.id, user_id=i, slot=n)
                    for n, i in enumerate((10, 20, 30), 1)
                )
                gid = group.id
            with local_api(url) as api:
                yield api, url, gid
        finally:
            engine.dispose()


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("kind", ["expenses", "settlements"])
def test_lost_tcp_response_replays_original_after_later_mutation(
    network: tuple[LocalAPI, URL, int], internal: bool, kind: str
) -> None:
    api, url, gid = network

    def auth(actor: int) -> dict[str, str]:
        return (
            {
                "X-Bot-Service-Token": api.environment["BOT_SERVICE_TOKEN"],
                "X-Telegram-ID": str(1000000 + actor),
            }
            if internal
            else {
                "Authorization": "Bearer "
                + create_access_token(actor, api.environment["JWT_SECRET_KEY"], 15)
            }
        )

    prefix = "/internal" if internal else ""
    original: list[dict[str, Any]] = []
    with httpx.Client(base_url=api.target, timeout=10, trust_env=False) as client:
        expense = {
            "title": "Network",
            "amount": "100.00",
            "split_mode": "equal",
            "participants": [20],
            "client_request_id": str(uuid4()),
        }
        if kind == "settlements":
            assert (
                client.post(
                    f"{prefix}/groups/{gid}/expenses", headers=auth(10), json=expense
                ).status_code
                == 201
            )
            payload: dict[str, Any] = {
                "receiver_id": 10,
                "amount": "50.00",
                "client_request_id": str(uuid4()),
            }
        else:
            payload = expense
        actor = 20 if kind == "settlements" else 10
        path = f"{prefix}/groups/{gid}/{kind}"

        class DropReply(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                data = self.rfile.read(int(self.headers["Content-Length"]))
                # Forward over TCP; wait for actual 201/commit, then close downstream
                # without even HTTP status headers. Simulates lost HTTP response.
                with httpx.Client(trust_env=False, timeout=10) as upstream:
                    result = upstream.post(
                        api.target + path,
                        content=data,
                        headers=auth(actor) | {"Content-Type": "application/json"},
                    )
                    assert result.status_code == 201
                    original.append(result.json())
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()

        with ThreadingHTTPServer(("127.0.0.1", 0), DropReply) as proxy:
            thread = Thread(target=proxy.handle_request)
            thread.start()
            try:
                with pytest.raises(httpx.RemoteProtocolError):
                    client.post(
                        f"http://127.0.0.1:{proxy.server_port}{path}", json=payload
                    )
            finally:
                thread.join(15)
            assert not thread.is_alive() and len(original) == 1
        first = client.post(path, headers=auth(actor), json=payload)
        assert first.status_code == 200 and first.json() == original[0]
        if kind == "expenses":
            eid = first.json()["expense"]["id"]
            changed = expense | {"amount": "60.00", "expected_version": 1}
            del changed["client_request_id"]
            assert (
                client.put(
                    f"{prefix}/expenses/{eid}", headers=auth(actor), json=changed
                ).status_code
                == 200
            )
            assert (
                client.post(path, headers=auth(actor), json=payload).json()
                == original[0]
            )
            assert (
                client.delete(
                    f"{prefix}/expenses/{eid}?expected_version=2", headers=auth(actor)
                ).status_code
                == 200
            )
        else:
            sid = first.json()["settlement"]["id"]
            terminal = client.post(
                f"{prefix}/settlements/{sid}/confirm", headers=auth(10)
            )
            assert terminal.status_code == 200
            assert (
                client.post(
                    f"{prefix}/settlements/{sid}/confirm", headers=auth(10)
                ).json()
                == terminal.json()
            )
            current = client.get(path, headers=auth(10)).json()["items"]
            assert current[0]["status"] == "confirmed"
        replay = client.post(path, headers=auth(actor), json=payload)
        assert replay.status_code == 200 and replay.json() == original[0]
        other = client.post(path, headers=auth(30), json=payload)
        assert (
            other.status_code == 409
            and other.json()["error"]["code"] == "request_conflict"
        )
        changed_intent = client.post(
            path, headers=auth(actor), json=payload | {"amount": "49.99"}
        )
        assert changed_intent.status_code == 409
    engine = create_engine(url, hide_parameters=True)
    try:
        with Session(engine) as session:
            model = Expense if kind == "expenses" else Settlement
            assert session.scalar(select(func.count()).select_from(model)) == 1
    finally:
        engine.dispose()


def test_load_runner_short_real_http_smoke(
    network: tuple[LocalAPI, URL, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from scripts import load_o08

    api, _, gid = network
    # Fast CI smoke only. Full 100-client measurements are separate explicit runs.
    monkeypatch.setattr(load_o08, "CLIENTS", 2)
    result = asyncio.run(
        load_o08.measure(
            api.target,
            [(gid, [10, 20, 30])],
            api.environment["JWT_SECRET_KEY"],
            0.15,
            99,
            max_requests=20,
        )
    )
    assert result["clients_started"] == result["peak_inflight"] == 2
    assert result["requests"] <= 20
    assert result["successful"] == result["requests"]
    assert result["statuses"].keys() <= {"200", "201"}
