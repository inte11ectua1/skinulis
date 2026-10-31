"""Trusted-main release policy and write-once SHA publication. Stdlib only."""

import argparse
import base64
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPOSITORY = "inte11ectua1/skinulis"
IMAGE = "ghcr.io/" + REPOSITORY
CHECKS = {"lint", "types", "tests", "docker-build", "ci"}


def sha(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("Expected a full lowercase commit SHA")
    return value


def command(args: list[str], *, data: str | None = None) -> str:
    result = subprocess.run(
        args, input=data, text=True, capture_output=True, timeout=900, check=False
    )
    if result.returncode:
        # Docker/SSH/HTTP diagnostics may include credentials. Never print them.
        raise RuntimeError(f"Release command failed: {args[0]}")
    return result.stdout.strip()


def github(path: str) -> dict[str, Any]:
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/{path}",
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        return cast(dict[str, Any], json.load(response))


def trusted_run(run: dict[str, Any], target: str) -> bool:
    return (
        run.get("head_sha") == target
        and run.get("head_branch") == "main"
        and run.get("head_repository", {}).get("full_name") == REPOSITORY
        and run.get("event") in {"push", "workflow_dispatch"}
        and run.get("path") == ".github/workflows/ci.yml"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )


def protected_environment(value: dict[str, Any]) -> bool:
    policy = value.get("deployment_branch_policy") or {}
    return (
        policy.get("protected_branches") is True
        and policy.get("custom_branch_policies") is False
        and any(
            rule.get("type") == "required_reviewers"
            and rule.get("prevent_self_review") is True
            and bool(rule.get("reviewers"))
            for rule in value.get("protection_rules", [])
        )
    )


def guard() -> None:
    if (
        os.environ["GITHUB_REPOSITORY"] != REPOSITORY
        or os.environ["GITHUB_REF"] != "refs/heads/main"
    ):
        raise ValueError("Releases require the canonical main workflow")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    kind = os.environ["GITHUB_EVENT_NAME"]
    if kind == "workflow_run":
        run = event["workflow_run"]
        target = sha(run["head_sha"])
        # The webhook may omit path; the authoritative API object is checked below.
        if not trusted_run(run | {"path": ".github/workflows/ci.yml"}, target):
            raise ValueError("Untrusted workflow_run source")
        run_id = int(run["id"])
    elif kind == "workflow_dispatch":
        target = sha(os.environ["INPUT_SHA"])
        runs = github(f"actions/workflows/ci.yml/runs?head_sha={target}&per_page=100")
        successful = [r for r in runs["workflow_runs"] if trusted_run(r, target)]
        if not successful:
            raise ValueError("No successful trusted main CI for this commit")
        run_id = int(successful[0]["id"])
    else:
        raise ValueError("Unsupported release event")
    command(["git", "fetch", "--no-tags", "origin", "main"])
    command(["git", "merge-base", "--is-ancestor", target, "origin/main"])
    run = github(f"actions/runs/{run_id}")
    jobs = github(f"actions/runs/{run_id}/jobs?per_page=100")["jobs"]
    if not trusted_run(run, target) or not CHECKS <= {
        j["name"] for j in jobs if j["conclusion"] == "success"
    }:
        raise ValueError("Required CI jobs did not all succeed")
    if os.environ.get("OPERATION") == "deploy":
        if (
            kind != "workflow_dispatch"
            or os.environ.get("ROLLOUT_ENABLED") != "true"
            or not protected_environment(github("environments/production"))
        ):
            raise ValueError("Production rollout is disabled or unprotected")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"sha={target}\nci_run={run_id}\n")


class Registry:
    def __init__(self) -> None:
        credentials = base64.b64encode(
            (os.environ["GITHUB_ACTOR"] + ":" + os.environ["GH_TOKEN"]).encode()
        ).decode()
        request = Request(
            f"https://ghcr.io/token?service=ghcr.io&scope=repository:{REPOSITORY}:pull,push",
            headers={"Authorization": "Basic " + credentials},
        )
        with urlopen(request, timeout=30) as response:
            self.token = json.load(response)["token"]

    def digest(self, target: str) -> str | None:
        request = Request(
            f"https://ghcr.io/v2/{REPOSITORY}/manifests/{sha(target)}",
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                value = str(response.headers.get("Docker-Content-Digest", ""))
        except HTTPError as error:
            # Only explicit MANIFEST_UNKNOWN means absent. Auth/network errors fail closed.
            if error.code == 404 and any(
                e.get("code") in {"MANIFEST_UNKNOWN", "NAME_UNKNOWN"}
                for e in json.load(error).get("errors", [])
            ):
                return None
            raise
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            raise ValueError("Invalid registry digest")
        return value


def publish(target: str) -> None:
    target = sha(target)
    registry = Registry()
    existing = registry.digest(target)
    if existing is None:
        command(
            [
                "docker",
                "build",
                "--pull",
                "--build-arg",
                f"APP_COMMIT_SHA={target}",
                "--tag",
                f"{IMAGE}:{target}",
                ".",
            ]
        )
        command(["docker", "push", f"{IMAGE}:{target}"])
        # A registry bearer may expire during a cold build; request a fresh one.
        existing = Registry().digest(target)
    if existing is None:
        raise ValueError("Published manifest is missing")
    pinned = f"{IMAGE}@{existing}"
    command(["docker", "pull", pinned])
    labels = json.loads(command(["docker", "image", "inspect", pinned]))[0]["Config"][
        "Labels"
    ]
    if (
        labels.get("org.opencontainers.image.revision") != target
        or labels.get("org.opencontainers.image.source")
        != f"https://github.com/{REPOSITORY}"
    ):
        raise ValueError("Registry image provenance mismatch")
    # Existing SHA tags are never overwritten, including on workflow re-run.
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"image={pinned}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["guard", "publish"])
    parser.add_argument("--sha", default="")
    args = parser.parse_args()
    try:
        if args.operation == "guard":
            guard()
        else:
            publish(args.sha)
    except Exception:
        print("Release refused or failed; no credential-bearing diagnostics emitted")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
