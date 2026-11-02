"""O-08 isolated infrastructure. Never imports operator .env or deploy settings."""

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]
OWNED = re.compile(r"skinulis_o08_[0-9a-f]{32}_test")


def validate_database(value: str, *, owned: bool = False) -> URL:
    """Reject external hosts, URL options and non-test databases BEFORE connecting."""
    try:
        url = make_url(value)
        valid = (
            url.drivername == "postgresql+psycopg"
            and url.host in {"127.0.0.1", "localhost"}
            and url.port is not None
            and url.username
            and url.password
            and url.database
            and not url.query
            and (
                OWNED.fullmatch(url.database)
                if owned
                else re.fullmatch(r"[a-zA-Z0-9_]+_test", url.database)
            )
        )
    except (ValueError, TypeError, ArgumentError):
        valid = False
    if not valid:
        raise ValueError(
            "Requires explicit loopback psycopg test database; no URL options"
        )
    return url


def validate_target(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.username
        or url.password
        or url.port is None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise ValueError("Only an explicit loopback HTTP API target is allowed")
    return value.rstrip("/")


def isolated_environment(url: URL) -> dict[str, str]:
    validate_database(url.render_as_string(hide_password=False), owned=True)
    # No inherited DATABASE_URL, JWT, service, Telegram or cloud credentials.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "LANG"}
    }
    environment.update(
        APP_ENV="test",
        DATABASE_URL=url.render_as_string(hide_password=False),
        JWT_SECRET_KEY=secrets.token_urlsafe(48),
        BOT_SERVICE_TOKEN=secrets.token_urlsafe(48),
        PYTHONUTF8="1",
    )
    return environment


@contextmanager
def disposable_database(configured: str) -> Iterator[URL]:
    admin_url = validate_database(configured)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    name = "skinulis_o08_" + uuid4().hex + "_test"
    created = False
    try:
        with admin.connect() as connection:
            version = int(
                connection.exec_driver_sql("SHOW server_version_num").scalar_one()
            )
            if not 170000 <= version < 180000:
                raise ValueError("Only PostgreSQL 17 is allowed")
            address = connection.exec_driver_sql(
                "SELECT host(inet_server_addr())"
            ).scalar_one()
            if not ip_address(address).is_private:
                raise ValueError(
                    "PostgreSQL server must be local/private (Docker bridge allowed)"
                )
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
        yield admin_url.set(database=name)
    finally:
        if created:
            assert OWNED.fullmatch(name)
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()


@dataclass
class LocalAPI:
    target: str
    environment: dict[str, str]
    process: subprocess.Popen[bytes]
    log_path: Path
    metrics_path: Path


@contextmanager
def local_api(url: URL, *, metrics: bool = False) -> Iterator[LocalAPI]:
    environment = isolated_environment(url)
    environment["APP_COMMIT_SHA"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    # Port is chosen locally; never accept an arbitrary caller-supplied target.
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    target = validate_target(f"http://127.0.0.1:{port}")
    with tempfile.TemporaryDirectory(prefix="skinulis-o08-") as folder:
        directory = Path(folder)
        log_path, metrics_path = directory / "api.log", directory / "metrics.json"
        environment["O08_STOP_DIR"] = str(directory)
        if metrics:
            environment["O08_METRICS_PATH"] = str(metrics_path)
        with log_path.open("wb") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "scripts.o08_support", str(port)],
                cwd=ROOT,
                env=environment,
                stdout=output,
                stderr=output,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt"
                else 0,
            )
            try:
                deadline = monotonic() + 30
                with httpx.Client(
                    trust_env=False, follow_redirects=False, timeout=1
                ) as client:
                    while True:
                        try:
                            response = client.get(target + "/health")
                            if response.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.poll() is not None or monotonic() > deadline:
                            raise RuntimeError(
                                "Isolated API startup failed; inspect local test log"
                            )
                        sleep(0.05)
                yield LocalAPI(target, environment, process, log_path, metrics_path)
            finally:
                # Test-only shutdown file watched by the owned server process.
                (directory / "stop").touch()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)


def serve(port: int) -> None:
    """One local Uvicorn worker, normal app/pool/thread defaults and T-10 logging."""
    import asyncio
    import threading
    from collections import defaultdict
    from time import perf_counter

    import uvicorn
    from sqlalchemy import event

    from app.config import Settings
    from app.main import create_app
    from skinulis_logging import configure_logging

    if os.environ.get("APP_ENV") != "test":
        raise ValueError("Test environment required")
    validate_database(os.environ["DATABASE_URL"], owned=True)
    configure_logging("api")
    app = create_app(Settings(_env_file=None))
    stats: dict[str, list[float]] = defaultdict(list)
    lock = threading.Lock()
    peaks = {"checked_out": 0}
    path = Path(os.environ.get("O08_METRICS_PATH", ""))
    # Metrics are diagnostic observers, no change to SQL, pool size or timeouts.
    lifespan = app.router.lifespan_context

    @contextmanager
    def listeners(engine: Any) -> Iterator[None]:
        def before(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            many: bool,
        ) -> None:
            context.o08_started = perf_counter()

        def after(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            many: bool,
        ) -> None:
            category = (
                "group_lock"
                if "FOR UPDATE" in statement and "FROM groups" in statement
                else "other"
            )
            with lock:
                stats[category].append((perf_counter() - context.o08_started) * 1000)

        def checkout(*args: Any) -> None:
            with lock:
                peaks["checked_out"] = max(
                    peaks["checked_out"], engine.pool.checkedout()
                )

        if "O08_METRICS_PATH" in os.environ:
            event.listen(engine, "before_cursor_execute", before)
            event.listen(engine, "after_cursor_execute", after)
            event.listen(engine, "checkout", checkout)
        yield

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def measured(application: Any) -> Any:
        async with lifespan(application):
            with listeners(application.state.database.engine):
                yield
        if "O08_METRICS_PATH" in os.environ:
            path.write_text(
                json.dumps({"sql_ms": stats, "pool_peak": peaks}), encoding="utf-8"
            )

    app.router.lifespan_context = measured
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, log_config=None, access_log=False
        )
    )
    # local_api always uses its TemporaryDirectory log for shutdown coordination.
    # A pipe-free signal works on Windows and Linux alike.
    stop_dir = Path(os.environ["O08_STOP_DIR"])

    async def run() -> None:
        async def monitor() -> None:
            if stop_dir is None:
                return
            while not (stop_dir / "stop").exists():
                await asyncio.sleep(0.1)
            server.should_exit = True

        task = asyncio.create_task(monitor())
        try:
            await server.serve()
        finally:
            task.cancel()

    asyncio.run(run())


if __name__ == "__main__":
    serve(int(sys.argv[1]))
