"""SSM boundaries and IAM templates: no real AWS calls or credentials in CI."""

import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts import ssm_proxy


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_INSTANCE_ID", "i-0123456789abcdef0")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")


def test_ssm_uses_only_ssh_document_and_fixed_port(target: None) -> None:
    assert ssm_proxy.command() == [
        "aws",
        "--region",
        "ap-southeast-2",
        "ssm",
        "start-session",
        "--target",
        "i-0123456789abcdef0",
        "--document-name",
        "AWS-StartSSHSession",
        "--parameters",
        "portNumber=22",
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("AWS_INSTANCE_ID", "host.example.com"),
        ("AWS_INSTANCE_ID", "i-0123456789abcdef0;echo unsafe"),
        ("AWS_INSTANCE_ID", "i-0123456789abcdef0\n"),
        ("AWS_REGION", "us-east-1"),
        ("AWS_REGION", "ap-southeast-2;echo unsafe"),
    ],
)
def test_ssm_invalid_target_never_executes(
    target: None,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
) -> None:
    monkeypatch.setenv(key, value)

    def forbidden(*args: Any) -> Any:
        pytest.fail("Must not open SSM")

    monkeypatch.setattr(os, "execvp", forbidden)
    assert ssm_proxy.main() == 1


def test_ssm_replaces_process_without_shell_or_token_output(
    target: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Replaced(BaseException):
        pass

    def execute(binary: str, args: list[str]) -> Any:
        assert binary == "aws"
        assert args == ssm_proxy.command()
        raise Replaced

    monkeypatch.setattr(os, "execvp", execute)
    with pytest.raises(Replaced):
        ssm_proxy.main()


def test_missing_aws_cli_fails_closed(
    target: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: Any) -> Any:
        raise FileNotFoundError("Missing AWS CLI")

    monkeypatch.setattr(os, "execvp", missing)
    assert ssm_proxy.main() == 1


def test_iam_templates_limit_identity_instance_and_session_ownership() -> None:
    root = Path(__file__).resolve().parents[2]
    trust = json.loads((root / "deploy/aws/github-oidc-trust.json").read_text())
    (statement,) = trust["Statement"]
    assert statement["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert statement["Condition"]["StringEquals"] == {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:inte11ectua1@105117564/skinulis@1421315056:environment:production",
    }
    policy = json.loads((root / "deploy/aws/github-ssm-permissions.json").read_text())
    by_action: dict[str, list[dict[str, Any]]] = {}
    for entry in policy["Statement"]:
        by_action.setdefault(entry["Action"], []).append(entry)
    assert set(by_action) == {
        "ssm:StartSession",
        "ssm:TerminateSession",
        "ssmmessages:OpenDataChannel",
    }
    assert {s["Resource"] for s in by_action["ssm:StartSession"]} == {
        "arn:aws:ec2:ap-southeast-2:<AWS_ACCOUNT_ID>:instance/<INSTANCE_ID>",
        "arn:aws:ssm:ap-southeast-2::document/AWS-StartSSHSession",
    }
    (terminate,) = by_action["ssm:TerminateSession"]
    assert terminate["Condition"]["StringEquals"] == {
        "ssm:resourceTag/aws:ssmmessages:target-id": "<INSTANCE_ID>",
        "ssm:resourceTag/aws:ssmmessages:session-id": "${aws:userid}",
    }
    # No long-lived IAM credentials, EC2/security-group edits, SendCommand or shell document.
    yaml = importlib.import_module("yaml")
    cd = yaml.safe_load((root / ".github/workflows/deploy.yml").read_text())
    aws_step = next(
        s
        for s in cd["jobs"]["deploy"]["steps"]
        if s.get("uses", "").startswith("aws-actions/")
    )
    assert "aws-access-key-id" not in aws_step["with"]
    assert "aws-secret-access-key" not in aws_step["with"]
