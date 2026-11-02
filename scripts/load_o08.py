"""Bounded O-08 real HTTP load. Only creates/drops its own UUID PostgreSQL 17 DB."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.security import create_access_token
from app.models import Group, GroupMember, User
from app.services import expense_crud
from app.services.expenses import ByItemsExpense, EqualExpense, ReceiptItemInput
from scripts.o08_support import ROOT, disposable_database, local_api, validate_target

CLIENTS = 100
SEED = 6108
# Fixed before first measurement: per client 4/10 balances, 2/10 plan,
# 1/10 expense page, 1/10 settlement page, 2/10 new expense POSTs.
OPERATIONS = (
    ("balances",) * 4
    + ("settlement-plan",) * 2
    + ("expenses", "settlements", "create", "create")
)


def percentile(values: list[float], percent: int) -> float:
    """Nearest rank, no interpolation. Latency floats are time, never money."""
    if not values:
        raise ValueError("No observations")
    return sorted(values)[max(0, math.ceil(len(values) * percent / 100) - 1)]


def summary(values: list[float]) -> dict[str, float | int]:
    return (
        {
            "count": len(values),
            "min_ms": min(values),
            "p50_ms": percentile(values, 50),
            "p95_ms": percentile(values, 95),
            "p99_ms": percentile(values, 99),
            "max_ms": max(values),
        }
        if values
        else {"count": 0}
    )


def seed_database(url: Any, groups: int) -> list[tuple[int, list[int]]]:
    engine = create_engine(url, hide_parameters=True)
    configuration = Config(str(ROOT / "alembic.ini"))
    configuration.attributes["safe_logging"] = True
    result = []
    try:
        from app.config import Settings

        previous_env_file = Settings.model_config.get("env_file")
        try:
            Settings.model_config["env_file"] = None
            command.upgrade(configuration, "head")
        finally:
            Settings.model_config["env_file"] = previous_env_file
        with Session(engine) as session:
            for g in range(groups):
                users = [g * 5 + i for i in range(1, 6)]
                session.add_all(
                    User(id=uid, telegram_id=1000000 + uid) for uid in users
                )
                session.flush()
                row = Group(
                    owner_id=users[0],
                    name="O08 synthetic",
                    client_request_id=UUID(int=g + 1),
                )
                session.add(row)
                session.flush()
                session.add_all(
                    GroupMember(group_id=row.id, user_id=uid, slot=i)
                    for i, uid in enumerate(users, 1)
                )
                session.commit()
                # Ten historical expenses/group, half receipts with heterogeneous consumers.
                for i in range(10):
                    draft = (
                        EqualExpense("O08 seed", "100.00", tuple(users))
                        if i % 2 == 0
                        else ByItemsExpense(
                            "O08 receipt",
                            (
                                ReceiptItemInput("Food", "30.01", tuple(users[:3])),
                                ReceiptItemInput("Tip", "0.02", tuple(users[2:])),
                            ),
                        )
                    )
                    expense_crud.create(
                        session,
                        row.id,
                        users[i % 5],
                        UUID(int=1000 + g * 10 + i),
                        draft,
                    )
                result.append((row.id, users))
    finally:
        engine.dispose()
    return result


async def measure(
    target: str,
    groups: list[tuple[int, list[int]]],
    key: str,
    seconds: float,
    phase: int,
    *,
    max_requests: int = 10000,
) -> dict[str, Any]:
    validate_target(target)
    ready = 0
    barrier = asyncio.Event()
    inflight = 0
    peak = 0
    completed = Counter[int]()
    started_clients: set[int] = set()
    statuses: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    latencies: list[float] = []
    per_operation: dict[str, list[float]] = {op: [] for op in set(OPERATIONS)}
    attempts = 0
    start = 0.0
    end = 0.0
    concurrency_samples: list[int] = []
    steady_samples: list[int] = []
    success_latencies: list[float] = []

    async def worker(index: int) -> None:
        nonlocal ready, inflight, peak, attempts, start, end
        group, members = groups[index % len(groups)]
        actor = members[(index // len(groups)) % len(members)]
        token = create_access_token(actor, key, 60)
        rng = random.Random(SEED + index)
        schedule = list(OPERATIONS)
        rng.shuffle(schedule)
        # One independent HTTP client/socket per active logical client. No proxy/retry.
        async with httpx.AsyncClient(
            base_url=target,
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=1, max_keepalive_connections=1, keepalive_expiry=60
            ),
            timeout=httpx.Timeout(15, connect=3),
        ) as client:
            ready += 1
            if ready == CLIENTS:
                start = perf_counter()
                end = start + seconds
                barrier.set()
            await barrier.wait()
            operation_index = 0
            while perf_counter() < end and attempts < max_requests:
                attempts += 1
                operation = schedule[operation_index % len(schedule)]
                operation_index += 1
                inflight += 1
                peak = max(peak, inflight)
                started_clients.add(index)
                stamp = perf_counter()
                try:
                    if operation == "create":
                        response = await client.post(
                            f"/groups/{group}/expenses",
                            json={
                                "title": "O08 synthetic",
                                "split_mode": "equal",
                                "amount": "1.01",
                                "participants": members,
                                "client_request_id": str(
                                    UUID(
                                        int=(phase + 1) * 10**12
                                        + index * 100000
                                        + operation_index
                                    )
                                ),
                            },
                        )
                    else:
                        response = await client.get(f"/groups/{group}/{operation}")
                    statuses[str(response.status_code)] += 1
                    if 200 <= response.status_code < 300:
                        success_latencies.append((perf_counter() - stamp) * 1000)
                    if response.status_code >= 400:
                        codes[
                            str(response.json().get("error", {}).get("code", "unknown"))
                        ] += 1
                except httpx.TimeoutException:
                    statuses["timeout"] += 1
                except httpx.TransportError:
                    statuses["network"] += 1
                finally:
                    elapsed = (perf_counter() - stamp) * 1000
                    latencies.append(elapsed)
                    per_operation[operation].append(elapsed)
                    completed[index] += 1
                    inflight -= 1

    async def sample() -> None:
        await barrier.wait()
        while any(not t.done() for t in workers):
            concurrency_samples.append(inflight)
            if perf_counter() < end:
                steady_samples.append(inflight)
            await asyncio.sleep(0.02)

    workers = [asyncio.create_task(worker(i)) for i in range(CLIENTS)]
    await asyncio.gather(*workers, sample())
    duration = perf_counter() - start
    return {
        "clients_started": len(started_clients),
        "clients_completed_requests": len(completed),
        "per_client_min_requests": min(completed.values()),
        "peak_inflight": peak,
        "sampled_inflight_min": min(concurrency_samples),
        "sampled_inflight_max": max(concurrency_samples),
        "sampled_inflight_mean": sum(concurrency_samples) / len(concurrency_samples),
        "samples": len(concurrency_samples),
        "steady_inflight_min": min(steady_samples, default=0),
        "steady_inflight_mean": sum(steady_samples) / len(steady_samples)
        if steady_samples
        else 0,
        "launch_window_seconds": seconds,
        "elapsed_including_drain_seconds": duration,
        "requests": len(latencies),
        "successful": sum(
            n for s, n in statuses.items() if s.isdigit() and 200 <= int(s) < 300
        ),
        "statuses": dict(statuses),
        "error_codes": dict(codes),
        "rps_including_drain": len(latencies) / duration,
        "latency": summary(latencies),
        "successful_latency": summary(success_latencies),
        "operations": {op: summary(v) for op, v in per_operation.items()},
        "target_pass": percentile(latencies, 95) <= 500
        and all(s.isdigit() and int(s) < 400 for s in statuses),
    }


def run(profile: str, warmup: float, duration: float) -> dict[str, Any]:
    configured = os.environ.get("TEST_DATABASE_URL", "")
    with disposable_database(configured) as url:
        # Only child/test migration settings; never load operator dotenv.
        from scripts.o08_support import isolated_environment

        environment = isolated_environment(url)
        previous = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update(environment)
            groups = seed_database(url, 20 if profile == "mixed" else 1)
        finally:
            os.environ.clear()
            os.environ.update(previous)
        observer = create_engine(
            url, hide_parameters=True, connect_args={"connect_timeout": 3}
        )
        with observer.connect() as connection:
            configuration = {
                name: connection.exec_driver_sql("SHOW " + name).scalar_one()
                for name in (
                    "server_version",
                    "max_connections",
                    "shared_buffers",
                    "fsync",
                    "synchronous_commit",
                    "full_page_writes",
                    "track_io_timing",
                )
            }
        lock_samples: list[int] = []
        active_samples: list[int] = []
        wait_events: Counter[str] = Counter()
        stop = False
        import threading

        def observe() -> None:
            while not stop:
                with observer.connect() as connection:
                    row = connection.execute(
                        text(
                            "SELECT count(*) FILTER (WHERE wait_event_type='Lock'), count(*) FILTER (WHERE state='active') FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()"
                        )
                    ).one()
                    lock_samples.append(row[0])
                    active_samples.append(row[1])
                    for wait_type, wait_event, count in connection.execute(
                        text(
                            "SELECT wait_event_type, wait_event, count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() GROUP BY wait_event_type,wait_event"
                        )
                    ):
                        wait_events[f"{wait_type}/{wait_event}"] += count
                # Event avoids an unbounded busy loop.
                threading.Event().wait(0.1)

        try:
            with local_api(url, metrics=True) as api:
                with httpx.Client(trust_env=False) as check:
                    assert (
                        check.get(api.target + "/version").json()["commit_sha"]
                        == api.environment["APP_COMMIT_SHA"]
                    )
                warm = asyncio.run(
                    measure(
                        api.target, groups, api.environment["JWT_SECRET_KEY"], warmup, 0
                    )
                )
                monitor = threading.Thread(target=observe)
                monitor.start()
                try:
                    result = asyncio.run(
                        measure(
                            api.target,
                            groups,
                            api.environment["JWT_SECRET_KEY"],
                            duration,
                            1,
                        )
                    )
                finally:
                    stop = True
                    monitor.join(5)
                (api.metrics_path.parent / "stop").touch()
                api.process.wait(timeout=15)
                diagnostics = json.loads(api.metrics_path.read_text(encoding="utf-8"))
                rawlog = api.log_path.read_text(encoding="utf-8")
                logs = [json.loads(line) for line in rawlog.splitlines()]
                # Privacy check uses synthetic secrets, never writes them to evidence.
                assert all(
                    secret not in rawlog
                    for secret in (
                        api.environment["JWT_SECRET_KEY"],
                        api.environment["BOT_SERVICE_TOKEN"],
                        str(url.password),
                    )
                )
                result["diagnostics_including_warmup"] = {
                    "pool_peak": diagnostics["pool_peak"],
                    "sql": {
                        name: summary(times)
                        for name, times in diagnostics["sql_ms"].items()
                    },
                    "safe_json_log_entries": len(logs),
                    "http_server_statuses": dict(
                        Counter(
                            str(e.get("status"))
                            for e in logs
                            if e["event"] == "http_request_completed"
                        )
                    ),
                    "max_pg_lock_waiters": max(lock_samples, default=0),
                    "max_pg_active": max(active_samples, default=0),
                    "pg_samples": len(lock_samples),
                    "pg_wait_event_observations": dict(wait_events),
                }
                result["warmup"] = warm
                result["postgresql"] = configuration
                result["profile"] = profile
                result["groups"] = len(groups)
                return result
        finally:
            observer.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("mixed", "contention"), required=True)
    parser.add_argument("--warmup", type=float, default=10)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0.1 <= args.warmup <= 30 or not 0.1 <= args.duration <= 120:
        parser.error("Warmup 0.1..30 s and duration 0.1..120 s only")
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    result = run(args.profile, args.warmup, args.duration)
    result.update(
        git_sha=sha,
        dirty=dirty,
        seed=SEED,
        os=platform.platform(),
        python=platform.python_version(),
        logical_cpus=os.cpu_count(),
        clients=CLIENTS,
        profile_schedule=list(OPERATIONS),
        workload="closed loop, no think time, no retries, 10k request cap per phase",
        http_pool="100 independent AsyncClients, one connection each, 15s timeout/connect3s, trust_env=False, no redirects",
        api="one Uvicorn worker, default AnyIO40 threads, INFO JSON logging enabled",
        db_pool="unchanged QueuePool size5+overflow10, timeout3s, pre_ping; statement_timeout3s/connect3s",
        source_sha256={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/load_o08.py",
                "scripts/o08_support.py",
                "app/db.py",
                "app/services/settlement_plan.py",
            )
        },
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "git_sha",
                    "profile",
                    "requests",
                    "statuses",
                    "latency",
                    "target_pass",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError):
        print(
            "O08 refused unsafe configuration or test infrastructure failed",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
