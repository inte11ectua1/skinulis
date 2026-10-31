"""VPS release controller. Dry-run by default; never downgrades or deletes data."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

from scripts.release import IMAGE, REPOSITORY, sha


def run(args: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(
        args, env=env, text=True, capture_output=True, timeout=900, check=False
    )
    if result.returncode:
        raise RuntimeError("Deployment command failed (output withheld)")
    return result.stdout.strip()


@dataclass(frozen=True)
class Release:
    sha: str
    image: str
    polling: bool = False

    def validate(self) -> None:
        sha(self.sha)
        if re.fullmatch(re.escape(IMAGE) + r"@sha256:[0-9a-f]{64}", self.image) is None:
            raise ValueError("Use the canonical image pinned by digest")


class Stack:
    def __init__(self, root: Path, release: Release) -> None:
        release.validate()
        self.release = release
        self.bundle = root / "releases" / release.sha
        config_file = root / "production.env"
        if (
            not config_file.is_file()
            or config_file.is_symlink()
            or config_file.stat().st_mode & 0o077
        ):
            raise ValueError("Use a private regular production.env file (mode 0600)")
        # The server env file is authoritative; shell variables must not redirect the DB.
        self.env = {
            key: os.environ[key]
            for key in (
                "PATH",
                "HOME",
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_CONFIG",
                "XDG_RUNTIME_DIR",
            )
            if key in os.environ
        }
        self.env["APP_IMAGE"] = release.image
        self.base = [
            "docker",
            "compose",
            "--env-file",
            str(root / "production.env"),
            "--project-directory",
            str(self.bundle / "deploy"),
            "-f",
            str(self.bundle / "deploy/compose.production.yaml"),
            "--profile",
            "polling",
        ]
        # Captured JSON may contain secrets. It never reaches stdout/logs/state files.
        self.config: dict[str, Any] = json.loads(
            self.compose("config", "--format", "json")
        )
        if self.config.get("name") != "skinulis-production":
            raise ValueError("Production project name must remain skinulis-production")
        values = self.config["services"]["api"]["environment"]
        domain = self.config["services"]["caddy"]["environment"]["PUBLIC_DOMAIN"]
        if re.fullmatch(
            r"(?=.{1,253}$)[a-z0-9]+(?:[.-][a-z0-9]+)+", domain
        ) is None or domain.endswith((".invalid", ".localhost")):
            raise ValueError("Set a public DNS domain without a scheme or path")
        self.domain: str = domain
        if any(
            re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", values[field]) is None
            for field in ("POSTGRES_DB", "POSTGRES_USER")
        ):
            raise ValueError("Use canonical PostgreSQL identifiers")
        jwt, bot, password = (
            values["JWT_SECRET_KEY"],
            values["BOT_SERVICE_TOKEN"],
            values["POSTGRES_PASSWORD"],
        )
        if (
            len(jwt.encode()) < 32
            or len(password.encode()) < 32
            or re.fullmatch(r"[A-Za-z0-9_-]{43,128}", bot) is None
            or len({jwt, bot, password}) != 3
        ):
            raise ValueError("Missing, invalid or reused runtime credentials")
        if (
            release.polling
            and re.fullmatch(
                r"[0-9]+:[A-Za-z0-9_-]{30,}",
                self.config["services"]["bot"]["environment"]["TELEGRAM_BOT_TOKEN"],
            )
            is None
        ):
            raise ValueError("Polling requires a separately configured Telegram token")

    def compose(self, *args: str) -> str:
        return run([*self.base, *args], self.env)

    def pull(self) -> None:
        run(["docker", "pull", self.release.image], self.env)
        info = json.loads(
            run(["docker", "image", "inspect", self.release.image], self.env)
        )[0]
        labels = info["Config"]["Labels"]
        if (
            labels.get("org.opencontainers.image.revision") != self.release.sha
            or labels.get("org.opencontainers.image.source")
            != "https://github.com/" + REPOSITORY
            or info["Config"]["User"] != "skinulis"
        ):
            raise ValueError("Wrong release image or runtime user")

    def revision(self) -> str | None:
        values = self.config["services"]["api"]["environment"]
        base = (
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            values["POSTGRES_USER"],
            "-d",
            values["POSTGRES_DB"],
            "-Atc",
        )
        if not self.compose(*base, "SELECT to_regclass('public.alembic_version')"):
            return None
        return self.compose(
            *base, "SELECT version_num FROM alembic_version ORDER BY version_num"
        )

    def api_up(self) -> None:
        self.compose("up", "-d", "--no-deps", "--wait", "api")
        self.compose("up", "-d", "--no-deps", "caddy")

    def probe(self) -> None:
        # Inspect real DB-backed health and the SHA embedded in the immutable image.
        code = (
            "import json,sys; from urllib.request import urlopen; "
            "h=json.load(urlopen('http://127.0.0.1:8000/health',timeout=5)); "
            "v=json.load(urlopen('http://127.0.0.1:8000/version',timeout=5)); "
            "assert h=={'status':'ok','database':'ok'}; assert v['commit_sha']==sys.argv[1]"
        )
        self.compose("exec", "-T", "api", "python", "-c", code, self.release.sha)
        deadline = time.monotonic() + 180
        while True:
            try:
                for path in ("/health", "/version"):
                    url = f"https://{self.domain}{path}"
                    with urlopen(url, timeout=5) as response:
                        if response.geturl() != url:
                            raise ValueError("Unexpected public redirect")
                        body = json.load(response)
                    expected = {"status": "ok", "database": "ok"}
                    if (path == "/health" and body != expected) or (
                        path == "/version"
                        and body.get("commit_sha") != self.release.sha
                    ):
                        raise ValueError("Public release probe mismatch")
                for path in ("/internal", "/internal/users/me", "/%69nternal/users/me"):
                    try:
                        with urlopen(f"https://{self.domain}{path}", timeout=5):
                            raise ValueError("Public internal route is exposed")
                    except HTTPError as error:
                        if error.code != 404:
                            raise ValueError(
                                "Internal route did not fail closed"
                            ) from None
                return
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "HTTPS/health/version/isolation probe failed"
                    ) from None
                time.sleep(3)


def write_state(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def deploy(
    root: Path, candidate: Release, *, rollback_compatible: bool = False
) -> None:
    state = root / "state"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Also serializes manual invocations on the VPS, independently of GitHub concurrency.
    with (state / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = state / "current.json"
        previous = (
            Release(**json.loads(current.read_text())) if current.exists() else None
        )
        stack = Stack(root, candidate)
        quiesced = False
        before: str | None = None
        try:
            print(f"Deploy {candidate.sha}: verify pinned image")
            stack.pull()
            # Run the actual image's validators BEFORE stopping a healthy old release.
            # These commands instantiate settings only; no API server or polling starts.
            stack.compose(
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "python",
                "api",
                "-c",
                "from app.config import Settings; s=Settings(_env_file=None); s.require_jwt_secret(); s.require_bot_service_token()",
            )
            if candidate.polling:
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "python",
                    "bot",
                    "-c",
                    "from bot.config import BotSettings; BotSettings(_env_file=None)",
                )
            print("Deploy: database health and schema preflight")
            stack.compose("up", "-d", "--no-deps", "--wait", "db")
            before = stack.revision()
            # A disconnected/killed previous SSH controller may leave its container alive.
            # Refuse to recreate it, even when that process no longer holds the host flock.
            for container in stack.compose(
                "ps", "--all", "--quiet", "migrate"
            ).splitlines():
                if (
                    run(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            "{{.State.Running}}",
                            container,
                        ],
                        stack.env,
                    )
                    != "false"
                ):
                    raise RuntimeError(
                        "An existing migrator still requires operator attention"
                    )
            if previous and (not before or "\n" in before):
                raise ValueError(
                    "Existing release requires one known database revision"
                )
            write_state(
                state / "attempt.json",
                {
                    "previous": asdict(previous) if previous else None,
                    "candidate": asdict(candidate),
                    "schema_before": before,
                },
            )
            quiesced = True
            stack.compose("stop", "bot", "api")
            print("Deploy: writers stopped; migrate once")
            # One foreground service, one migration invocation. No API worker migrates.
            stack.compose(
                "up",
                "--no-deps",
                "--force-recreate",
                "--abort-on-container-exit",
                "--exit-code-from",
                "migrate",
                "migrate",
            )
            stack.api_up()
            print("Deploy: verify DB-backed health, public HTTPS, isolation and SHA")
            stack.probe()
            if candidate.polling:
                stack.compose("up", "-d", "--no-deps", "--wait", "bot")
            if previous:
                write_state(state / "previous.json", asdict(previous))
            write_state(current, asdict(candidate))
        except Exception:
            if quiesced:
                stack.compose("stop", "bot", "api")
                # Unknown/new schema is NOT evidence that an old image remains compatible.
                after = stack.revision()
                if previous and (after == before or rollback_compatible):
                    old = Stack(root, previous)
                    old.pull()
                    old.api_up()
                    old.probe()
                    if previous.polling and candidate.polling:
                        old.compose("up", "-d", "--no-deps", "--wait", "bot")
                else:
                    raise RuntimeError(
                        "Stopped safely; operator must assess schema compatibility"
                    ) from None
            raise RuntimeError(
                "Release failed; successful state was not advanced"
            ) from None


def rollback(root: Path, *, compatible: bool, polling: bool = False) -> None:
    """Operator-approved image rollback; NEVER run old migrations on a newer DB."""
    if not compatible:
        raise ValueError("Review schema compatibility before an explicit rollback")
    state = root / "state"
    with (state / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = json.loads((state / "current.json").read_text())
        previous = Release(**json.loads((state / "previous.json").read_text()))
        target = Release(previous.sha, previous.image, previous.polling and polling)
        stack = Stack(root, target)
        stack.pull()
        if not stack.revision():
            raise ValueError("Rollback requires a known existing database schema")
        stack.compose("stop", "bot", "api")
        try:
            stack.api_up()
            stack.probe()
            if target.polling:
                stack.compose("up", "-d", "--no-deps", "--wait", "bot")
        except Exception:
            stack.compose("stop", "bot", "api")
            raise
        write_state(state / "previous.json", current)
        write_state(state / "current.json", asdict(target))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sha", default="")
    parser.add_argument("--image", default="")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--enable-polling", action="store_true")
    parser.add_argument("--rollback-compatible", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.rollback:
            current = Release(**json.loads((root / "state/current.json").read_text()))
            if Path(__file__).resolve().parents[1] != root / "releases" / current.sha:
                raise ValueError("Run rollback from the current verified bundle")
            if not args.execute:
                print(
                    "Dry-run: previous image only; compatibility approval required; no migration"
                )
                return 0
            rollback(
                root, compatible=args.rollback_compatible, polling=args.enable_polling
            )
            print("Previous image restored and verified; database schema unchanged")
            return 0
        candidate = Release(args.sha, args.image, args.enable_polling)
        candidate.validate()
        if Path(__file__).resolve().parents[1] != root / "releases" / candidate.sha:
            raise ValueError(
                "Install the verified bundle under root/releases/SHA first"
            )
        if not args.execute:
            Stack(root, candidate)
            print(
                "Dry-run: validate digest/config; pull; DB health; stop writers; migrate once; API; HTTPS/SHA; optional polling; record release"
            )
            return 0
        deploy(root, candidate, rollback_compatible=args.rollback_compatible)
    except Exception:
        print(
            "Deployment refused/failed. Inspect container state locally without exporting secrets."
        )
        return 1
    print("Release health, HTTPS isolation and SHA verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
