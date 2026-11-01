"""Configure safe logging before Uvicorn imports or starts the application."""

import logging

import uvicorn

from skinulis_logging import Event, configure_logging, emit


def main() -> None:
    configure_logging("api")
    try:
        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host="0.0.0.0",
            port=8000,
            log_config=None,
            access_log=False,
        )
    except Exception:
        emit(Event.API_FAILED, level=logging.ERROR)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
