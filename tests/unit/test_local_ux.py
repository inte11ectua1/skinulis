"""Local launcher fails closed without production endpoints or implicit polling."""

import subprocess
from pathlib import Path

import pytest

from scripts import local_ux


def test_init_is_private_separate_and_never_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "private" / "ux.env"
    local_ux.init(target)
    values = local_ux.environment(target)
    assert target.stat().st_mode & 0o777 == 0o600
    assert values["TELEGRAM_BOT_TOKEN"] == ""
    assert values["COMPOSE_PROJECT_NAME"].startswith("skinulis-ux84-")
    assert (
        len(
            {
                values[k]
                for k in ("BOT_SERVICE_TOKEN", "JWT_SECRET_KEY", "POSTGRES_PASSWORD")
            }
        )
        == 3
    )
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        local_ux.init(target)
    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("POSTGRES_DB", "skinulis"),
        ("APP_ENV", "prod"),
        ("API_PORT", "80"),
        ("API_BASE_URL", "https://production.invalid"),
        ("DATABASE_URL", "postgresql://elsewhere"),
        ("COMPOSE_PROJECT_NAME", "skinulis-production"),
        ("LOCAL_UX_IMAGE", "ghcr.io/inte11ectua1/skinulis:main"),
    ],
)
def test_config_refuses_production_redirects(
    tmp_path: Path, key: str, value: str
) -> None:
    p = tmp_path / "local.env"
    local_ux.init(p)
    values = local_ux.environment(p)
    values[key] = value
    p.write_text("\n".join(k + "=" + v for k, v in values.items()) + "\n")
    with pytest.raises(ValueError):
        local_ux.environment(p)


def test_insecure_or_symlink_env_refused(tmp_path: Path) -> None:
    p = tmp_path / "local.env"
    local_ux.init(p)
    p.chmod(0o644)
    with pytest.raises(ValueError):
        local_ux.environment(p)
    p.chmod(0o600)
    link = tmp_path / "alias.env"
    link.symlink_to(p)
    with pytest.raises(ValueError):
        local_ux.environment(link)


def test_no_telegram_or_container_start_without_explicit_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / "local.env"
    local_ux.init(p)
    commands: list[list[str]] = []

    def run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "unix:///var/run/docker.sock", "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "0" * 40)
    monkeypatch.setattr(
        local_ux.sys if hasattr(local_ux, "sys") else __import__("sys"),
        "argv",
        ["local_ux", "start-bot", "--env-file", str(p)],
    )
    assert local_ux.main() == 1
    assert not any("up" in c for c in commands)
    assert "--allow-test-polling" in capsys.readouterr().out


def test_remote_docker_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "ssh://example.invalid")
    with pytest.raises(ValueError):
        local_ux.local_docker({})


@pytest.mark.parametrize("operation", ["build", "status"])
def test_build_never_restarts_and_status_only_prints_safe_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
) -> None:
    import json
    import sys

    p = tmp_path / "local.env"
    local_ux.init(p)
    private = local_ux.environment(p)["BOT_SERVICE_TOKEN"]
    commands: list[list[str]] = []

    def run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        output = (
            "unix:///var/run/docker.sock"
            if "context" in args
            else json.dumps(
                [
                    {
                        "Service": "bot",
                        "State": "running",
                        "Health": "",
                        "Command": private,
                    }
                ]
            )
        )
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "0" * 40)
    monkeypatch.setattr(sys, "argv", ["local_ux", operation, "--env-file", str(p)])
    assert local_ux.main() == 0
    assert not any("up" in c or "stop" in c or "restart" in c for c in commands)
    out = capsys.readouterr().out
    assert private not in out
    if operation == "status":
        assert '"State": "running"' in out and '"Command"' not in out
    else:
        assert commands[-1][-2:] == ["build", "api"]
