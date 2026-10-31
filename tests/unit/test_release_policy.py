"""No GitHub/registry writes: exercise release trust boundaries with mocked APIs."""

import importlib
import io
import json
import os
import secrets
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from scripts import release

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def run_data() -> dict[str, Any]:
    return dict(
        id=99,
        head_sha=SHA,
        head_branch="main",
        head_repository=dict(full_name=release.REPOSITORY),
        event="push",
        path=".github/workflows/ci.yml",
        status="completed",
        conclusion="success",
    )


def environment() -> dict[str, Any]:
    return dict(
        deployment_branch_policy=dict(
            protected_branches=True, custom_branch_policies=False
        ),
        protection_rules=[
            dict(
                type="required_reviewers",
                prevent_self_review=True,
                reviewers=[dict(type="User", reviewer=dict(login="reviewer"))],
            )
        ],
    )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "main",
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "g" * 40,
        "a" * 40 + "\n",
        "$(touch unsafe)",
    ],
)
def test_full_sha_validation(value: str) -> None:
    with pytest.raises(ValueError):
        release.sha(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("head_sha", "c" * 40),
        ("head_branch", "feature"),
        ("event", "pull_request"),
        ("event", "pull_request_target"),
        ("head_repository", {"full_name": "fork/skinulis"}),
        ("path", ".github/workflows/other.yml"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", "skipped"),
    ],
)
def test_untrusted_ci_cannot_authorize_release(field: str, value: Any) -> None:
    assert not release.trusted_run(run_data() | {field: value}, SHA)


def test_protected_environment_requires_another_reviewer_and_branch_policy() -> None:
    assert release.protected_environment(environment())
    for field, value in (("protection_rules", []), ("deployment_branch_policy", None)):
        assert not release.protected_environment(environment() | {field: value})
    for field, invalid in (("reviewers", []), ("prevent_self_review", False)):
        config = environment()
        config["protection_rules"][0][field] = invalid
        assert not release.protected_environment(config)


@pytest.fixture
def guard_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    event, output = tmp_path / "event.json", tmp_path / "output"
    event.write_text(json.dumps(dict(workflow_run=run_data())))
    for key, value in dict(
        GITHUB_EVENT_PATH=str(event),
        GITHUB_OUTPUT=str(output),
        GITHUB_REPOSITORY=release.REPOSITORY,
        GITHUB_REF="refs/heads/main",
        GITHUB_EVENT_NAME="workflow_run",
        INPUT_SHA=SHA,
        OPERATION="publish",
    ).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(release, "command", lambda *a, **kw: "")
    return output


def api(path: str) -> dict[str, Any]:
    if path.startswith("actions/workflows/"):
        return {"workflow_runs": [run_data()]}
    if "/jobs?" in path:
        return {
            "jobs": [dict(name=name, conclusion="success") for name in release.CHECKS]
        }
    if path == "environments/production":
        return environment()
    return run_data()


@pytest.mark.parametrize("kind", ["workflow_run", "workflow_dispatch"])
def test_guard_proves_exact_ci_and_main_ancestry(
    guard_env: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", kind)
    monkeypatch.setattr(release, "github", api)
    commands: list[list[str]] = []

    def command(args: list[str]) -> str:
        commands.append(args)
        return ""

    monkeypatch.setattr(release, "command", command)
    if kind == "workflow_run":
        # GitHub webhooks do not necessarily include the workflow path.
        data = run_data()
        data.pop("path")
        Path(os.environ["GITHUB_EVENT_PATH"]).write_text(
            json.dumps(dict(workflow_run=data))
        )
    release.guard()
    assert guard_env.read_text() == f"sha={SHA}\nci_run=99\n"
    assert ["git", "merge-base", "--is-ancestor", SHA, "origin/main"] in commands


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_REPOSITORY", "fork/skinulis"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_EVENT_NAME", "pull_request"),
    ],
)
def test_wrong_workflow_context_is_denied(
    guard_env: Path, monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        release.guard()
    assert not guard_env.exists()


@pytest.mark.parametrize("bad", ["ci", "tests", "docker-build"])
def test_missing_or_failed_required_job_blocks_publish(
    guard_env: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    def failing(path: str) -> dict[str, Any]:
        response = api(path)
        if "jobs" in response:
            response["jobs"] = [
                j | {"conclusion": "skipped"} if j["name"] == bad else j
                for j in response["jobs"]
            ]
        return response

    monkeypatch.setattr(release, "github", failing)
    with pytest.raises(ValueError):
        release.guard()


@pytest.mark.parametrize("enabled", [False, True])
def test_deploy_needs_explicit_flag_and_protected_environment(
    guard_env: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("OPERATION", "deploy")
    monkeypatch.setenv("ROLLOUT_ENABLED", "true" if enabled else "false")
    monkeypatch.setattr(release, "github", api)
    if enabled:
        release.guard()
        assert guard_env.exists()
    else:
        with pytest.raises(ValueError):
            release.guard()


def test_deploy_refuses_unprotected_environment(
    guard_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("OPERATION", "deploy")
    monkeypatch.setenv("ROLLOUT_ENABLED", "true")
    monkeypatch.setattr(
        release,
        "github",
        lambda path: {} if path == "environments/production" else api(path),
    )
    with pytest.raises(ValueError):
        release.guard()


@pytest.mark.parametrize("existing", [True, False])
def test_published_sha_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    registry = object.__new__(release.Registry)
    replies = iter([DIGEST] if existing else [None, DIGEST])
    monkeypatch.setattr(registry, "digest", lambda value: next(replies))
    monkeypatch.setattr(release, "Registry", lambda: registry)
    commands: list[list[str]] = []

    def command(args: list[str]) -> str:
        commands.append(args)
        if args[1:3] == ["image", "inspect"]:
            return json.dumps(
                [
                    dict(
                        Config=dict(
                            Labels={
                                "org.opencontainers.image.revision": SHA,
                                "org.opencontainers.image.source": "https://github.com/"
                                + release.REPOSITORY,
                            }
                        )
                    )
                ]
            )
        return ""

    monkeypatch.setattr(release, "command", command)
    release.publish(SHA)
    assert output.read_text() == f"image={release.IMAGE}@{DIGEST}\n"
    assert sum(args[1] == "push" for args in commands) == (0 if existing else 1)
    assert sum(args[1] == "build" for args in commands) == (0 if existing else 1)
    assert all(":latest" not in arg for args in commands for arg in args)


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "UNAUTHORIZED"), (403, "DENIED"), (500, "UNKNOWN"), (404, "OTHER")],
)
def test_registry_errors_are_not_treated_as_absent_tags(
    monkeypatch: pytest.MonkeyPatch, status: int, code: str
) -> None:
    registry = object.__new__(release.Registry)
    registry.token = secrets.token_urlsafe(32)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise HTTPError(
            "https://ghcr.io/test",
            status,
            "redacted",
            Message(),
            io.BytesIO(json.dumps({"errors": [{"code": code}]}).encode()),
        )

    monkeypatch.setattr(release, "urlopen", fail)
    with pytest.raises(HTTPError):
        registry.digest(SHA)


def test_workflows_keep_pr_secrets_out_and_deploy_manual_only() -> None:
    # PyYAML is already locked through pre-commit; no extra dependency is introduced.
    yaml = importlib.import_module("yaml")
    root = Path(__file__).resolve().parents[2]
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    cd = yaml.safe_load((root / ".github/workflows/deploy.yml").read_text())
    assert "pull_request" in ci[True] and "push" in ci[True]
    assert "secrets." not in (root / ".github/workflows/ci.yml").read_text()
    assert not {"pull_request", "pull_request_target"} & cd[True].keys()
    assert cd["permissions"] == {}
    assert cd["concurrency"]["cancel-in-progress"] is False
    assert cd["jobs"]["publish"]["permissions"]["packages"] == "write"
    deploy = cd["jobs"]["deploy"]
    assert deploy["environment"] == "production"
    assert (
        "workflow_dispatch" in deploy["if"]
        and "PRODUCTION_ROLLOUT_ENABLED" in deploy["if"]
    )
    assert cd[True]["workflow_dispatch"]["inputs"]["enable_polling"]["default"] is False
    for job in cd["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert len(step["uses"].split("@")[1]) == 40
