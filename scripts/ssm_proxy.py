"""SSH ProxyCommand: one AWS SSH session, with no shell or direct-TCP fallback."""

import os
import re


def command() -> list[str]:
    target, region = os.environ["AWS_INSTANCE_ID"], os.environ["AWS_REGION"]
    if re.fullmatch(r"i-[0-9a-f]{17}", target) is None or region != "ap-southeast-2":
        raise ValueError("Invalid SSM destination")
    return [
        "aws",
        "--region",
        region,
        "ssm",
        "start-session",
        "--target",
        target,
        "--document-name",
        "AWS-StartSSHSession",
        "--parameters",
        "portNumber=22",
    ]


def main() -> int:
    try:
        args = command()
        # The AWS CLI/plugin own stdin/stdout (the SSH byte stream). Never print
        # session tokens or JSON here. SSH's parent captures diagnostic stderr.
        os.execvp(args[0], args)
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
