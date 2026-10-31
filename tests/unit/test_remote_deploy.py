"""SSH is always mocked; no server or actual credentials are used."""

import io
import secrets
import subprocess
import tarfile
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from scripts import remote_deploy as remote
from scripts.release import IMAGE


@pytest.fixture
def ssh_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for file in (
        "deploy/compose.production.yaml",
        "deploy/Caddyfile",
        "scripts/__init__.py",
        "scripts/release.py",
        "scripts/deployment.py",
    ):
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test bundle")
    for key, value in dict(
        PRODUCTION_ROLLOUT_ENABLED="true",
        RELEASE_SHA="a" * 40,
        APP_IMAGE=IMAGE + "@sha256:" + "b" * 64,
        SSH_HOST="host.example.invalid",
        SSH_USER="skinulis",
        SSH_PORT="22",
        SSH_DEPLOY_DIR="/opt/skinulis",
        SSH_PRIVATE_KEY=secrets.token_urlsafe(48),
        SSH_KNOWN_HOSTS=secrets.token_urlsafe(48),
        ENABLE_POLLING="false",
    ).items():
        monkeypatch.setenv(key, value)


def test_pinned_ssh_bundle_contains_no_env_or_credentials(
    ssh_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    bundles: list[bytes] = []

    def run(args: list[str], **kwargs: Any) -> CompletedProcess[bytes]:
        calls.append(args)
        if kwargs["input"]:
            bundles.append(kwargs["input"])
        return CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert remote.main() == 0
    assert len(calls) == 2
    assert all(
        "StrictHostKeyChecking=yes" in args and "BatchMode=yes" in args
        for args in calls
    )
    assert "--enable-polling" not in calls[-1][-1]
    with tarfile.open(fileobj=io.BytesIO(bundles[0])) as archive:
        assert len(archive.getnames()) == 5
        assert not any(".env" in name or "key" in name for name in archive.getnames())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PRODUCTION_ROLLOUT_ENABLED", "false"),
        ("SSH_HOST", "-oProxyCommand=bad"),
        ("SSH_HOST", "host;command"),
        ("SSH_USER", "user@host"),
        ("SSH_PORT", "22;command"),
        ("SSH_DEPLOY_DIR", "/opt/../etc"),
        ("SSH_DEPLOY_DIR", "/opt/path with space"),
        ("SSH_PRIVATE_KEY", ""),
        ("SSH_KNOWN_HOSTS", ""),
    ],
)
def test_invalid_or_disabled_transport_never_connects(
    ssh_env: None, monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("SSH must not run")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert remote.main() == 1


def test_ssh_failure_is_not_success_and_does_not_leak(
    ssh_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = secrets.token_urlsafe(48)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: CompletedProcess(args, 1, b"", secret.encode()),
    )
    assert remote.main() == 1
    assert secret not in capsys.readouterr().out
