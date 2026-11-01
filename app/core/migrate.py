"""Одноразовая команда миграций; Compose запускает её перед API."""

import logging
from pathlib import Path

from alembic.config import Config

from alembic import command
from skinulis_logging import Event, configure_logging, emit


def main() -> int:
    configure_logging("api")
    configuration = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    configuration.attributes["safe_logging"] = True
    emit(Event.MIGRATION_STARTED)
    try:
        command.upgrade(configuration, "head")
    except Exception:
        # A failed migration must block startup, without exposing connection data.
        emit(Event.MIGRATION_FAILED, level=logging.ERROR)
        return 1
    emit(Event.MIGRATION_COMPLETED)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
