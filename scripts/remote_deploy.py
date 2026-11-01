"""Approved Environment-only SSH transport. Never invoked by PR CI."""

import argparse
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from scripts.deployment import Release
from scripts.ssm_proxy import command as ssm_command


def aws_identity() -> None:
    """Reject absent/other AWS credentials before opening an SSM session."""
    role = os.environ["AWS_ROLE_ARN"]
    match = re.fullmatch(
        r"arn:aws:iam::([0-9]{12}):role/skinulis-github-production", role
    )
    session = os.environ["AWS_ROLE_SESSION_NAME"]
    if match is None or re.fullmatch(r"skinulis-gh-[0-9]+-[0-9]+", session) is None:
        raise ValueError("Invalid deployment role")
    ssm_command()  # Validate region/target before any AWS API call.
    result = subprocess.run(
        ["aws", "sts", "get-caller-identity", "--output", "json"],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("AWS credentials unavailable")
    identity = json.loads(result.stdout)
    if (
        identity.get("Account") != match[1]
        or identity.get("Arn")
        != f"arn:aws:sts::{match[1]}:assumed-role/skinulis-github-production/{session}"
    ):
        raise ValueError("Unexpected AWS principal")


def main(*, check_only: bool = False) -> int:
    try:
        if (
            os.environ.get("GITHUB_REPOSITORY") != "inte11ectua1/skinulis"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        ):
            raise ValueError("Untrusted workflow context")
        if not check_only and os.environ.get("PRODUCTION_ROLLOUT_ENABLED") != "true":
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
            or user != "skinulis-deploy"
            or port != "22"
            or re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+", root) is None
        ):
            raise ValueError("Invalid SSH destination")
        # Transport comes from the workflow commit; bundle/controller come from
        # the separately guarded release checkout, including for older releases.
        bundle = io.BytesIO()
        with tarfile.open(fileobj=bundle, mode="w") as archive:
            for file in (
                ()
                if check_only
                else (
                    "deploy/compose.production.yaml",
                    "deploy/Caddyfile",
                    "scripts/__init__.py",
                    "scripts/release.py",
                    "scripts/deployment.py",
                )
            ):
                path = Path(os.environ.get("RELEASE_BUNDLE_DIR", ".")) / file
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
            aws_identity()
            proxy = Path(__file__).resolve().with_name("ssm_proxy.py")
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
                "IdentityAgent=none",
                "-o",
                "PreferredAuthentications=publickey",
                "-o",
                "HostKeyAlgorithms=ssh-ed25519",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={hosts}",
                "-o",
                "GlobalKnownHostsFile=/dev/null",
                "-o",
                f"HostKeyAlias={host}",
                "-o",
                "CheckHostIP=no",
                "-o",
                "ProxyCommand=" + shlex.join([sys.executable, str(proxy)]),
                "-o",
                "ConnectTimeout=10",
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "ForwardAgent=no",
                "-o",
                "ClearAllForwardings=yes",
                f"{user}@{os.environ['AWS_INSTANCE_ID']}",
            ]
            if check_only:
                # Read-only diagnostics only; no bundle, Docker run, DB or controller.
                result = subprocess.run(
                    [
                        *ssh,
                        f'test "$(id -un)" = {user} && test -d {shlex.quote(root)} '
                        '&& docker version --format "{{.Server.Version}}" >/dev/null',
                    ],
                    input=b"",
                    capture_output=True,
                    timeout=90,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError("SSM/SSH connection check failed")
                print("Approved read-only SSM/SSH connection check completed")
                return 0
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-connection", action="store_true")
    raise SystemExit(main(check_only=parser.parse_args().check_connection))
