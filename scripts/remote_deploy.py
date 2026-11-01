"""Approved Environment-only SSH transport. Never invoked by PR CI."""

import io
import os
import re
import shlex
import subprocess
import tarfile
import tempfile
from pathlib import Path

from scripts.deployment import Release


def main() -> int:
    try:
        if os.environ.get("PRODUCTION_ROLLOUT_ENABLED") != "true":
            raise ValueError("Rollout disabled")
        target = Release(
            os.environ["RELEASE_SHA"],
            os.environ["APP_IMAGE"],
            os.environ.get("ENABLE_POLLING") == "true",
        )
        target.validate()
        host, user, port, root = (
            os.environ[name]
            for name in ("SSH_HOST", "SSH_USER", "SSH_PORT", "SSH_DEPLOY_DIR")
        )
        if (
            re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", host) is None
            or re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user) is None
            or not port.isdecimal()
            or not 1 <= int(port) <= 65535
            or re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+", root) is None
        ):
            raise ValueError("Invalid SSH destination")
        # Fixed bundle allowlist: no .env, Git credentials, host files or symbolic links.
        bundle = io.BytesIO()
        with tarfile.open(fileobj=bundle, mode="w") as archive:
            for file in (
                "deploy/compose.production.yaml",
                "deploy/Caddyfile",
                "scripts/__init__.py",
                "scripts/release.py",
                "scripts/deployment.py",
                "scripts/backup_postgres.py",
            ):
                path = Path(file)
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Invalid release bundle")
                archive.add(path, arcname=file, recursive=False)
        with tempfile.TemporaryDirectory() as temporary:
            key, hosts = Path(temporary) / "key", Path(temporary) / "known_hosts"
            for path, name in ((key, "SSH_PRIVATE_KEY"), (hosts, "SSH_KNOWN_HOSTS")):
                value = os.environ[name]
                if not value.strip():
                    raise ValueError("Missing SSH configuration")
                path.write_text(value + "\n")
                path.chmod(0o600)
            ssh = [
                "ssh",
                "-F",
                "/dev/null",
                "-i",
                str(key),
                "-p",
                port,
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={hosts}",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "ForwardAgent=no",
                "-o",
                "ClearAllForwardings=yes",
                f"{user}@{host}",
            ]
            release = f"{root}/releases/{target.sha}"
            commands = [
                (
                    f"install -d -m 750 {shlex.quote(release)} && tar -xf - -C {shlex.quote(release)}",
                    bundle.getvalue(),
                ),
            ]
            args = [
                "python3",
                "-m",
                "scripts.deployment",
                "--root",
                root,
                "--sha",
                target.sha,
                "--image",
                target.image,
                "--execute",
            ]
            if target.polling:
                args.append("--enable-polling")
            if os.environ.get("ROLLBACK_COMPATIBLE") == "true":
                args.append("--rollback-compatible")
            commands.append((f"cd {shlex.quote(release)} && {shlex.join(args)}", b""))
            for command, data in commands:
                result = subprocess.run(
                    [*ssh, command],
                    input=data,
                    capture_output=True,
                    timeout=1800,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError("SSH transport/deployment failed")
    except Exception:
        print(
            "Remote deployment refused/failed; credentials and remote output withheld"
        )
        return 1
    print("Approved remote release completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
