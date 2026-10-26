"""uv run python scripts/test_integration.py [pytest options]. Requires Docker."""

import os
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    environment = os.environ.copy()
    password = secrets.token_urlsafe(32)
    environment["POSTGRES_TEST_PASSWORD"] = password
    project = "skinulis-t03-tests-" + uuid4().hex[:12]
    compose = ["docker", "compose", "-p", project, "-f", "compose.test.yaml"]
    try:
        subprocess.run(
            [*compose, "up", "-d", "--wait"], cwd=ROOT, env=environment, check=True
        )
        binding = subprocess.check_output(
            [*compose, "port", "db-test", "5432"],
            cwd=ROOT,
            env=environment,
            text=True,
        ).strip()
        port = int(binding.rsplit(":", 1)[1])
        environment["TEST_DATABASE_URL"] = URL.create(
            "postgresql+psycopg",
            username="skinulis_test",
            password=password,
            host="127.0.0.1",
            port=port,
            database="skinulis_test",
        ).render_as_string(hide_password=False)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-m", "integration", *sys.argv[1:]],
            cwd=ROOT,
            env=environment,
            check=False,
        )
        return result.returncode
    finally:
        # This UUID-named project owns only a tmpfs test DB, no persistent volumes.
        subprocess.run([*compose, "down"], cwd=ROOT, env=environment, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
