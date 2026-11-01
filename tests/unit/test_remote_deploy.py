"""SSH is always mocked; no server or actual credentials are used."""

import io
import json
import secrets
import subprocess
import tarfile
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from scripts import remote_deploy as remote
from scripts.release import IMAGE

AWS_IDENTITY = remote.aws_identity


@pytest.fixture
def ssh_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for file in (
        "deploy/compose.production.yaml",
        "deploy/Caddyfile",
        "scripts/__init__.py",
        "scripts/release.py",
        "scripts/deployment.py",
        "scripts/backup_postgres.py",
    ):
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test bundle")
    for key, value in dict(
        PRODUCTION_ROLLOUT_ENABLED="true",
        RELEASE_SHA="a" * 40,
        APP_IMAGE=IMAGE + "@sha256:" + "b" * 64,
        SSH_HOST="host.example.invalid",
        SSH_USER="skinulis-deploy",
        SSH_PORT="22",
        SSH_DEPLOY_DIR="/opt/skinulis",
        SSH_PRIVATE_KEY=secrets.token_urlsafe(48),
        SSH_KNOWN_HOSTS=secrets.token_urlsafe(48),
        ENABLE_POLLING="false",
        GITHUB_REPOSITORY="inte11ectua1/skinulis",
        GITHUB_REF="refs/heads/main",
        GITHUB_EVENT_NAME="workflow_dispatch",
        AWS_ROLE_ARN="arn:aws:iam::123456789012:role/skinulis-github-production",
        AWS_ROLE_SESSION_NAME="skinulis-gh-123-1",
        AWS_INSTANCE_ID="i-0123456789abcdef0",
        AWS_REGION="ap-southeast-2",
    ).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(remote, "aws_identity", lambda: None)


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
    assert all(
        "HostKeyAlias=host.example.invalid" in args
        and "HostKeyAlgorithms=ssh-ed25519" in args
        and "GlobalKnownHostsFile=/dev/null" in args
        and any(arg.startswith("ProxyCommand=") for arg in args)
        and args[-2] == "skinulis-deploy@i-0123456789abcdef0"
        for args in calls
    )
    assert "--enable-polling" not in calls[-1][-1]
    with tarfile.open(fileobj=io.BytesIO(bundles[0])) as archive:
        assert len(archive.getnames()) == 6
        assert "scripts/backup_postgres.py" in archive.getnames()
        assert not any(".env" in name or "key" in name for name in archive.getnames())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PRODUCTION_ROLLOUT_ENABLED", "false"),
        ("SSH_HOST", "-oProxyCommand=bad"),
        ("SSH_HOST", "host;command"),
        ("SSH_USER", "user@host"),
        ("SSH_USER", "ubuntu"),
        ("SSH_PORT", "22;command"),
        ("SSH_PORT", "5432"),
        ("SSH_DEPLOY_DIR", "/opt/../etc"),
        ("SSH_DEPLOY_DIR", "/opt/path with space"),
        ("SSH_PRIVATE_KEY", ""),
        ("SSH_KNOWN_HOSTS", ""),
        ("GITHUB_REPOSITORY", "fork/skinulis"),
        ("GITHUB_REF", "refs/pull/99/merge"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("RELEASE_SHA", "untrusted"),
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


@pytest.mark.parametrize(
    "error",
    [b"AccessDeniedException", b"TargetNotConnected", b"Host key verification failed"],
)
def test_failed_ssm_or_host_key_never_runs_controller_or_falls_back(
    ssh_env: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: bytes,
) -> None:
    calls: list[list[str]] = []

    def fail(args: list[str], **kwargs: Any) -> CompletedProcess[bytes]:
        calls.append(args)
        return CompletedProcess(args, 255, b"", error)

    monkeypatch.setattr(subprocess, "run", fail)
    assert remote.main() == 1
    assert len(calls) == 1
    assert "scripts.deployment" not in calls[0][-1]
    assert "ProxyCommand=" in " ".join(calls[0])
    assert error.decode() not in capsys.readouterr().out


def test_read_only_check_with_rollout_disabled_sends_no_bundle_or_controller(
    ssh_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTION_ROLLOUT_ENABLED", "false")
    monkeypatch.setenv("RELEASE_BUNDLE_DIR", "/does/not/exist")
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> CompletedProcess[bytes]:
        calls.append(args)
        assert kwargs["input"] == b""
        return CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert remote.main(check_only=True) == 0
    assert len(calls) == 1
    assert "docker version" in calls[0][-1]
    assert not any(word in calls[0][-1] for word in ("--execute", "tar", "migrate"))


@pytest.mark.parametrize(
    "failure", ["valid", "denied", "account", "role", "session", "json"]
)
def test_aws_identity_is_required_and_matches_expected_role(
    ssh_env: None, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # Exercise the real identity validator (the network boundary stays mocked).
    identity = dict(
        Account="123456789012",
        Arn="arn:aws:sts::123456789012:assumed-role/skinulis-github-production/skinulis-gh-123-1",
    )
    if failure == "account":
        identity["Account"] = "111111111111"
    if failure == "role":
        identity["Arn"] = identity["Arn"].replace(
            "skinulis-github-production", "another-role"
        )
    if failure == "session":
        identity["Arn"] += "-other"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: CompletedProcess(
            [],
            1 if failure == "denied" else 0,
            b"invalid" if failure == "json" else json.dumps(identity).encode(),
        ),
    )
    if failure == "valid":
        AWS_IDENTITY()
    else:
        with pytest.raises((ValueError, RuntimeError)):
            AWS_IDENTITY()


def test_missing_aws_permissions_prevent_any_ssh_command(
    ssh_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def denied(args: list[str], **kwargs: Any) -> CompletedProcess[bytes]:
        calls.append(args)
        assert args[0] == "aws"
        return CompletedProcess(args, 1, b"", b"AccessDenied")

    monkeypatch.setattr(remote, "aws_identity", AWS_IDENTITY)
    monkeypatch.setattr(subprocess, "run", denied)
    assert remote.main() == 1
    assert len(calls) == 1


def test_transport_uses_guarded_bundle_not_current_workflow_files(
    ssh_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = tmp_path / "release"
    for file in (
        "deploy/compose.production.yaml",
        "deploy/Caddyfile",
        "scripts/__init__.py",
        "scripts/release.py",
        "scripts/deployment.py",
        "scripts/backup_postgres.py",
    ):
        path = release / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("guarded release content")
    monkeypatch.setenv("RELEASE_BUNDLE_DIR", str(release))
    bundles: list[bytes] = []

    def run(args: list[str], **kwargs: Any) -> CompletedProcess[bytes]:
        if kwargs["input"]:
            bundles.append(kwargs["input"])
        return CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert remote.main() == 0
    with tarfile.open(fileobj=io.BytesIO(bundles[0])) as archive:
        member = archive.extractfile("scripts/deployment.py")
        assert member is not None
        assert member.read() == b"guarded release content"
