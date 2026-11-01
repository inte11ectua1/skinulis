"""Manual private PostgreSQL dump for T-09; never restores or deletes data."""

import argparse
import fcntl
import os
import re
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def backup(directory: Path, project: str = "skinulis-production") -> Path:
    if (
        project != "skinulis-production"
        and re.fullmatch(r"skinulis-backup-test-[0-9a-f]{12}", project) is None
    ):
        raise ValueError("Use the production project or a disposable backup test")
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise ValueError("Backup directory must be owned by this user, mode 0700")
    lock_fd = os.open(
        directory / ".backup.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        containers = subprocess.run(
            [
                "docker",
                "ps",
                "--quiet",
                "--no-trunc",
                "--filter",
                "label=com.docker.compose.project=" + project,
                "--filter",
                "label=com.docker.compose.service=db",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.splitlines()
        if len(containers) != 1 or re.fullmatch(r"[0-9a-f]{64}", containers[0]) is None:
            raise ValueError("Expected exactly one running database container")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = directory / f"{stamp}-{uuid4().hex}.dump"
        partial = target.with_suffix(".partial")
        created_partial = False
        try:
            fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_partial = True
            with os.fdopen(fd, "wb") as output:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        containers[0],
                        "sh",
                        "-ec",
                        'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                        "--format=custom --no-owner --no-acl",
                    ],
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=900,
                    check=False,
                )
                output.flush()
                os.fsync(output.fileno())
            if result.returncode or partial.stat().st_size == 0:
                raise RuntimeError("Database dump failed; raw diagnostics withheld")
            with partial.open("rb") as source:
                result = subprocess.run(
                    ["docker", "exec", "-i", containers[0], "pg_restore", "--list"],
                    stdin=source,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=60,
                    check=False,
                )
            if result.returncode:
                raise RuntimeError("Dump archive validation failed")
            # Link atomically without replacing any existing backup, then unlink our temp.
            os.link(partial, target)
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        finally:
            if created_partial:
                partial.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--project", default="skinulis-production")
    args = parser.parse_args()
    try:
        result = backup(args.directory, args.project)
    except Exception:
        print("Backup refused/failed; database and credentials were not printed")
        return 1
    print(f"Validated private dump: {result.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
