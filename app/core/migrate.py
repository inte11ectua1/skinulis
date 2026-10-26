"""Одноразовая команда миграций; Compose запускает её перед API."""

import logging
from pathlib import Path

from alembic.config import Config

from alembic import command


def main() -> int:
    configuration = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    try:
        command.upgrade(configuration, "head")
    except Exception:
        # A failed migration must block startup, without exposing connection data.
        logging.getLogger(__name__).error(
            "Database migration failed; API startup is blocked. Check DB and migrations."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
