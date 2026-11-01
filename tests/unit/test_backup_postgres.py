"""Backup failure boundaries: privacy, exact source and no destructive restore."""

import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from scripts import backup_postgres


@pytest.mark.parametrize(
    "project", ["", "other", "skinulis-production-other", "x;true"]
)
def test_rejects_unapproved_projects(tmp_path: Path, project: str) -> None:
    with pytest.raises(ValueError, match="project|test"):
        backup_postgres.backup(tmp_path, project)


def test_refuses_shared_directory_and_symlink(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="0700"):
        backup_postgres.backup(shared)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="0700"):
        backup_postgres.backup(link)


@pytest.mark.parametrize("containers", ["", "a" * 64 + "\n" + "b" * 64, "bad-id"])
def test_requires_one_exact_running_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, containers: str
) -> None:
    tmp_path.chmod(0o700)
    calls: list[list[str]] = []

    def invoke(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, containers)

    monkeypatch.setattr("scripts.backup_postgres.subprocess.run", invoke)
    with pytest.raises(ValueError, match="exactly one"):
        backup_postgres.backup(tmp_path)
    assert len(calls) == 1
    assert "label=com.docker.compose.project=skinulis-production" in calls[0]
    assert "label=com.docker.compose.service=db" in calls[0]
    assert not list(tmp_path.glob("*.dump"))


@pytest.mark.parametrize("failure", [None, "dump", "archive"])
def test_dump_is_private_atomic_and_never_restores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    tmp_path.chmod(0o700)
    original = tmp_path / "previous.dump"
    original.write_bytes(b"previous backup")
    calls: list[list[str]] = []

    def invoke(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, "a" * 64 + "\n")
        if "pg_restore" in args:
            assert args[-1] == "--list"
            assert kwargs["stdin"].read() == b"PGDMP synthetic archive"
            return subprocess.CompletedProcess(args, int(failure == "archive"))
        assert args[:3] == ["docker", "exec", "a" * 64]
        assert "--no-owner --no-acl" in args[-1]
        kwargs["stdout"].write(b"PGDMP synthetic archive")
        return subprocess.CompletedProcess(args, int(failure == "dump"))

    monkeypatch.setattr("scripts.backup_postgres.subprocess.run", invoke)
    if failure:
        with pytest.raises(RuntimeError):
            backup_postgres.backup(tmp_path)
        assert list(tmp_path.glob("*.dump")) == [original]
    else:
        result = backup_postgres.backup(tmp_path)
        assert result.read_bytes() == b"PGDMP synthetic archive"
        assert stat.S_IMODE(result.stat().st_mode) == 0o600
        assert len(list(tmp_path.glob("*.dump"))) == 2
    assert original.read_bytes() == b"previous backup"
    assert not list(tmp_path.glob("*.partial"))
    assert all(
        "--clean" not in command and "dropdb" not in command for command in calls
    )


def test_cli_withholds_raw_database_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["backup", "--directory", str(tmp_path)])

    def fail(*args: object, **kwargs: object) -> Path:
        raise RuntimeError("sensitive database diagnostic")

    monkeypatch.setattr(backup_postgres, "backup", fail)
    assert backup_postgres.main() == 1
    assert "sensitive database diagnostic" not in capsys.readouterr().out


def test_filename_collision_preserves_existing_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)

    class Clock:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return datetime(2026, 11, 1, tzinfo=UTC)

    monkeypatch.setattr(backup_postgres, "datetime", Clock)
    monkeypatch.setattr(backup_postgres, "uuid4", lambda: UUID(int=0))
    monkeypatch.setattr(
        "scripts.backup_postgres.subprocess.run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "a" * 64),
    )
    existing = tmp_path / ("20261101T000000Z-" + "0" * 32 + ".partial")
    existing.write_bytes(b"previous interrupted backup")
    with pytest.raises(FileExistsError):
        backup_postgres.backup(tmp_path)
    assert existing.read_bytes() == b"previous interrupted backup"
