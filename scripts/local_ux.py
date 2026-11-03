"""Isolated Mac test stack. No production destination, automatic volume deletion or live start."""

import argparse
import json
import os
import re
import secrets
import socket
import stat
import subprocess
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = Path.home() / ".config/skinulis/ux84.env"


def environment(path: Path) -> dict[str, str]:
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
    ):
        raise ValueError("Use a private regular env file with mode 0600")
    # Our generated file deliberately uses simple KEY=value, no shell interpolation.
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, sep, value = line.partition("=")
            if not sep or not re.fullmatch("[A-Z_]+", key):
                raise ValueError("Invalid local configuration")
            values[key] = value
    project = values.get("COMPOSE_PROJECT_NAME", "")
    if re.fullmatch(r"skinulis-ux84-[a-f0-9]{12}", project) is None:
        raise ValueError("Refusing a non-test Compose project")
    if (
        values.get("POSTGRES_DB") != "skinulis_ux84"
        or values.get("POSTGRES_USER") != "skinulis_ux84"
        or values.get("APP_ENV") != "test"
    ):
        raise ValueError("Use the isolated generated database settings")
    if values.get("LOCAL_UX_IMAGE") != project + ":local":
        raise ValueError("Use a project-specific local image")
    if set(values) - {
        "COMPOSE_PROJECT_NAME",
        "LOCAL_UX_IMAGE",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "JWT_SECRET_KEY",
        "BOT_SERVICE_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "APP_ENV",
        "API_PORT",
    }:
        raise ValueError("Unexpected environment fields; production URLs are forbidden")
    if (
        not values.get("API_PORT", "").isascii()
        or not values["API_PORT"].isdigit()
        or not 1024 <= int(values["API_PORT"]) <= 65535
    ):
        raise ValueError("Invalid loopback port")
    return values


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    project = "skinulis-ux84-" + secrets.token_hex(6)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    values = {
        "COMPOSE_PROJECT_NAME": project,
        "LOCAL_UX_IMAGE": project + ":local",
        "APP_ENV": "test",
        "POSTGRES_DB": "skinulis_ux84",
        "POSTGRES_USER": "skinulis_ux84",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(48),
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "BOT_SERVICE_TOKEN": secrets.token_urlsafe(48),
        "API_PORT": str(port),
        "TELEGRAM_BOT_TOKEN": "",
    }
    # Exclusive creation never overwrites user files or a previously supplied token.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(
            "# Local test bot only: fill TELEGRAM_BOT_TOKEN yourself. Never commit this file.\n"
            + "\n".join(k + "=" + v for k, v in values.items())
            + "\n"
        )
    print("Private local env created:", path)


def local_docker(env: dict[str, str]) -> None:
    if os.environ.get("DOCKER_HOST", "").startswith(("tcp:", "ssh:", "http:")):
        raise ValueError("Remote Docker daemon is forbidden")
    r = subprocess.run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    if not r.stdout.strip().startswith("unix://"):
        raise ValueError("Use the Mac local Docker socket")


def local_health(values: dict[str, str]) -> None:
    """Fail before contacting Telegram if the isolated API/database is unavailable."""
    with build_opener(ProxyHandler({})).open(
        "http://127.0.0.1:" + values["API_PORT"] + "/health", timeout=5
    ) as response:
        if json.load(response) != {"status": "ok", "database": "ok"}:
            raise ValueError("Local API/database health check failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=["init", "up", "check", "start-bot", "stop-bot", "stop", "status"],
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT)
    parser.add_argument(
        "--allow-test-polling",
        action="store_true",
        help="Explicit owner consent; only use after configuring the separate test token",
    )
    args = parser.parse_args()
    try:
        source = args.env_file.expanduser()
        path = source.parent.resolve() / source.name
        if path.is_relative_to(ROOT):
            raise ValueError("Keep the private env outside the Git checkout")
        if args.operation == "init":
            init(path)
            return 0
        values = environment(path)
        # No inherited application/Compose values can redirect the stack.
        env = {
            k: os.environ[k]
            for k in (
                "PATH",
                "HOME",
                "DOCKER_CONTEXT",
                "DOCKER_CONFIG",
                "XDG_RUNTIME_DIR",
            )
            if k in os.environ
        }
        env["APP_COMMIT_SHA"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        local_docker(env)
        compose = [
            "docker",
            "compose",
            "--env-file",
            str(path),
            "-p",
            values["COMPOSE_PROJECT_NAME"],
            "-f",
            "compose.yaml",
            "-f",
            "compose.ux.yaml",
            "--profile",
            "polling",
        ]
        if args.operation == "check":
            subprocess.run(
                [*compose, "config", "--quiet"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
            )
            local_health(values)
            print(
                json.dumps(
                    {
                        "local_health": "PASS",
                        "telegram_token_present": bool(
                            values.get("TELEGRAM_BOT_TOKEN")
                        ),
                        "telegram_requested": False,
                    }
                )
            )
            return 0
        if args.operation == "start-bot":
            if not args.allow_test_polling:
                raise ValueError(
                    "Explicit --allow-test-polling is required; no Telegram request was made"
                )
            if not values.get("TELEGRAM_BOT_TOKEN"):
                raise ValueError(
                    "Owner must fill the separate test token; value is never printed"
                )
            local_health(values)
            # A fixed container name makes repeated up converge to one process.
            command = ["up", "-d", "--no-deps", "bot"]
        elif args.operation == "up":
            command = ["up", "-d", "--build", "db", "migrate", "api"]
        elif args.operation == "stop-bot":
            command = ["stop", "--timeout", "30", "bot"]
        elif args.operation == "stop":
            command = ["stop", "--timeout", "30"]
        else:
            command = ["ps", "-a"]
        subprocess.run(
            [*compose, *command], cwd=ROOT, env=env, check=True, capture_output=True
        )
        print(
            "Local operation completed:",
            args.operation,
            "project:",
            values["COMPOSE_PROJECT_NAME"],
        )
        if args.operation == "up":
            print("Loopback API: http://127.0.0.1:" + values["API_PORT"])
        return 0
    except ValueError as error:
        print(str(error))
        return 1
    except Exception:
        # Tool failures can include interpolated env values: never print raw stderr.
        print(
            "Local operation refused/failed. Check local Docker, private env and owner consent; raw configuration/output withheld."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
