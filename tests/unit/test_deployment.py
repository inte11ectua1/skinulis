"""Exercise deployment failures/state/rollback without touching a real Docker stack."""

import fcntl
import io
import json
import secrets
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from scripts import deployment as d
from scripts.release import IMAGE

OLD = d.Release("a" * 40, IMAGE + "@sha256:" + "b" * 64, True)
NEW = d.Release("c" * 40, IMAGE + "@sha256:" + "d" * 64)


@pytest.mark.parametrize(
    "image",
    [
        IMAGE + ":latest",
        IMAGE + ":" + "a" * 40,
        "ghcr.io/fork/app@sha256:" + "b" * 64,
        IMAGE + "@sha256:short",
    ],
)
def test_deployment_requires_pinned_canonical_image(image: str) -> None:
    with pytest.raises(ValueError):
        d.Release(NEW.sha, image).validate()


@pytest.fixture
def stack_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    config_file = tmp_path / "production.env"
    config_file.touch(mode=0o600)
    config: dict[str, Any] = {
        "name": "skinulis-production",
        "services": {
            "api": {
                "environment": dict(
                    POSTGRES_DB="skinulis",
                    POSTGRES_USER="skinulis",
                    POSTGRES_PASSWORD=secrets.token_urlsafe(48),
                    JWT_SECRET_KEY=secrets.token_urlsafe(48),
                    BOT_SERVICE_TOKEN=secrets.token_urlsafe(48),
                )
            },
            "caddy": {"environment": {"PUBLIC_DOMAIN": "api.example.org"}},
            "bot": {
                "environment": {
                    "TELEGRAM_BOT_TOKEN": "123456:" + secrets.token_urlsafe(32)
                }
            },
        },
    }
    monkeypatch.setattr(d, "run", lambda *args: json.dumps(config))
    return config


@pytest.mark.parametrize("bad", ["", "x" * 31, "same"])
def test_runtime_credentials_fail_without_disclosure(
    tmp_path: Path, stack_config: dict[str, Any], bad: str
) -> None:
    values = stack_config["services"]["api"]["environment"]
    values["JWT_SECRET_KEY"] = bad
    with pytest.raises(ValueError, match="credentials"):
        d.Stack(tmp_path, NEW)


def test_reused_service_secret_and_unstable_project_are_refused(
    tmp_path: Path, stack_config: dict[str, Any]
) -> None:
    values = stack_config["services"]["api"]["environment"]
    values["BOT_SERVICE_TOKEN"] = values["JWT_SECRET_KEY"]
    with pytest.raises(ValueError):
        d.Stack(tmp_path, NEW)
    stack_config["name"] = "accidentally-new-project"
    with pytest.raises(ValueError, match="project"):
        d.Stack(tmp_path, NEW)


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "api.example.invalid",
        "https://api.example.org",
        "example.org/path",
        "example.org;command",
    ],
)
def test_public_domain_validation(
    tmp_path: Path, stack_config: dict[str, Any], domain: str
) -> None:
    stack_config["services"]["caddy"]["environment"]["PUBLIC_DOMAIN"] = domain
    with pytest.raises(ValueError):
        d.Stack(tmp_path, NEW)


@pytest.fixture
def controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]]:
    state = tmp_path / "state"
    state.mkdir()
    d.write_state(state / "current.json", asdict(OLD))
    calls: list[tuple[str, tuple[str, ...]]] = []
    scenario: dict[str, Any] = {
        "fail": None,
        "schema_changed": False,
        "revision_calls": 0,
    }

    class FakeStack:
        def __init__(self, root: Path, release: d.Release) -> None:
            self.release = release
            self.env: dict[str, str] = {}

        def compose(self, *args: str) -> str:
            calls.append((self.release.sha, args))
            if args[0] == "ps" and scenario.get("running_migrator"):
                return "mock-container"
            phase = (
                "migrate"
                if args[0] == "up" and args[-1:] == ("migrate",)
                else "bot"
                if args[-1:] == ("bot",) and args[0] == "up"
                else None
            )
            if self.release.sha == NEW.sha and phase and scenario["fail"] == phase:
                raise RuntimeError("Simulated Docker failure")
            return ""

        def pull(self) -> None:
            calls.append((self.release.sha, ("pull",)))
            if self.release.sha == NEW.sha and scenario["fail"] == "pull":
                raise RuntimeError("Image missing")

        def revision(self) -> str:
            scenario["revision_calls"] += 1
            return (
                "new_schema"
                if scenario["schema_changed"] and scenario["revision_calls"] > 1
                else "old_schema"
            )

        def api_up(self) -> None:
            calls.append((self.release.sha, ("api_up",)))
            if self.release.sha == NEW.sha and scenario["fail"] == "api":
                raise RuntimeError("API unhealthy")

        def probe(self) -> None:
            calls.append((self.release.sha, ("probe",)))
            if self.release.sha == NEW.sha and scenario["fail"] == "probe":
                raise RuntimeError("Wrong public SHA")

    monkeypatch.setattr(d, "Stack", FakeStack)
    return tmp_path, calls, scenario


def test_release_stops_writers_migrates_once_and_records_success(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
) -> None:
    root, calls, _ = controller
    d.deploy(root, NEW)
    assert json.loads((root / "state/current.json").read_text()) == asdict(NEW)
    assert json.loads((root / "state/previous.json").read_text()) == asdict(OLD)
    commands = [args for _, args in calls]
    migration = [
        args for args in commands if args[0] == "up" and args[-1:] == ("migrate",)
    ]
    assert len(migration) == 1
    assert (
        commands.index(("stop", "bot", "api"))
        < commands.index(migration[0])
        < commands.index(("api_up",))
        < commands.index(("probe",))
    )
    assert all(
        not set(args) & {"down", "prune", "downgrade", "-v"} for args in commands
    )
    assert (root / "state/current.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("phase", ["pull", "migrate", "api", "probe", "bot"])
def test_failure_preserves_state_and_rolls_back_only_image(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
    phase: str,
) -> None:
    root, calls, scenario = controller
    scenario["fail"] = phase
    with pytest.raises(RuntimeError):
        d.deploy(root, d.Release(NEW.sha, NEW.image, True))
    assert json.loads((root / "state/current.json").read_text()) == asdict(OLD)
    if phase == "pull":
        assert (OLD.sha, ("api_up",)) not in calls
    else:
        assert (OLD.sha, ("api_up",)) in calls
        assert (OLD.sha, ("probe",)) in calls
    assert all("downgrade" not in args and "down" not in args for _, args in calls)


@pytest.mark.parametrize("approved", [False, True])
def test_new_schema_requires_explicit_rollback_compatibility(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
    approved: bool,
) -> None:
    root, calls, scenario = controller
    scenario.update(fail="probe", schema_changed=True)
    with pytest.raises(RuntimeError):
        d.deploy(root, NEW, rollback_compatible=approved)
    assert ((OLD.sha, ("api_up",)) in calls) is approved
    assert json.loads((root / "state/current.json").read_text()) == asdict(OLD)


def test_server_file_lock_blocks_parallel_migrators(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
) -> None:
    root, calls, _ = controller
    with (root / "state/deploy.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            d.deploy(root, NEW)
    assert not calls


def test_rollback_does_not_enable_polling_without_current_permission(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
) -> None:
    root, calls, scenario = controller
    scenario["fail"] = "probe"
    with pytest.raises(RuntimeError):
        d.deploy(root, NEW)
    assert not any(
        target == OLD.sha and args[-1:] == ("bot",) and args[0] == "up"
        for target, args in calls
    )


def test_default_command_is_dry_run(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, calls, _ = controller
    monkeypatch.setattr(
        d, "__file__", str(root / "releases" / NEW.sha / "scripts/deployment.py")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["deployment", "--root", str(root), "--sha", NEW.sha, "--image", NEW.image],
    )
    assert d.main() == 0
    assert not calls


@pytest.mark.parametrize("approved", [False, True])
def test_manual_rollback_skips_migrations_and_requires_compatibility(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
    approved: bool,
) -> None:
    root, calls, _ = controller
    d.write_state(root / "state/previous.json", asdict(NEW))
    if not approved:
        with pytest.raises(ValueError):
            d.rollback(root, compatible=False)
        assert not calls
    else:
        d.rollback(root, compatible=True)
        assert json.loads((root / "state/current.json").read_text()) == asdict(NEW)
        assert not any("migrate" in args or "downgrade" in args for _, args in calls)


def test_orphaned_running_migrator_is_never_recreated(
    controller: tuple[Path, list[tuple[str, tuple[str, ...]]], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, calls, scenario = controller
    scenario["running_migrator"] = True
    monkeypatch.setattr(d, "run", lambda *args: "true")
    with pytest.raises(RuntimeError):
        d.deploy(root, NEW)
    assert not any(
        args[0] == "stop" or (args[0] == "up" and args[-1:] == ("migrate",))
        for _, args in calls
    )


def test_wrong_version_fails_public_health_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = object.__new__(d.Stack)
    stack.release, stack.domain = NEW, "api.example.org"
    monkeypatch.setattr(stack, "compose", lambda *args: "")

    class Response(io.StringIO):
        def __init__(self, url: str) -> None:
            self.url = url
            super().__init__(
                json.dumps(
                    {"status": "ok", "database": "ok"}
                    if url.endswith("/health")
                    else {"commit_sha": OLD.sha}
                )
            )

        def geturl(self) -> str:
            return self.url

    monkeypatch.setattr(
        d,
        "urlopen",
        lambda url, **kwargs: Response(url),
    )
    clock = iter([0.0, 181.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="probe failed"):
        stack.probe()
