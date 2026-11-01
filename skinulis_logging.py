"""Shared stdout projection: only fixed events and explicitly safe fields are logged.

Bot imports infrastructure only; this module has no DB/API/financial dependencies.
Raw messages, formatting arguments, exception strings and arbitrary extras are never
serialized. The record factory also protects third-party/capture handlers.
"""

import json
import logging
import sys
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, TextIO
from uuid import UUID, uuid4


class Event(StrEnum):
    HTTP_COMPLETED = "http_request_completed"
    HTTP_FAILED = "http_request_failed"
    DATABASE_UNAVAILABLE = "database_unavailable"
    API_STARTED = "api_started"
    API_STOPPED = "api_stopped"
    API_FAILED = "api_runtime_failed"
    MIGRATION_STARTED = "migration_started"
    MIGRATION_COMPLETED = "migration_completed"
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    BOT_CONFIG_INVALID = "bot_configuration_invalid"
    BOT_FAILED = "bot_runtime_failed"
    BOT_UPDATE_FAILED = "bot_update_failed"
    BOT_HANDLER_FAILED = "bot_handler_failed"
    TELEGRAM_DELIVERY_FAILED = "telegram_delivery_failed"
    CLIENT_FAILED = "http_client_failed"
    CLIENT_COMPLETED = "http_client_completed"
    LIBRARY = "library_event"
    TELEGRAM = "telegram_transport_failure"
    DATABASE = "database_driver_event"
    NOTIFICATION_CLAIM_FAILED = "notification_claim_failed"
    NOTIFICATION_DELIVERY_FAILED = "notification_delivery_failed"
    MIGRATION_FAILED = "migration_failed"


class Outcome(StrEnum):
    OK = "ok"
    INPUT = "input"
    AUTH = "auth"
    FORBIDDEN = "forbidden"
    MISSING = "missing"
    CONFLICT = "conflict"
    SERVER = "server"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UNEXPECTED = "unexpected"
    RETRY = "retry"
    TELEGRAM = "telegram"


@dataclass(frozen=True)
class Fields:
    status: int | None = None
    method: str | None = None
    route: str | None = None
    duration_ms: int | None = None
    outcome: Outcome | None = None
    request_id: str | None = None


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_routes: frozenset[str] = frozenset()
_original_factory: Callable[..., logging.LogRecord] = logging.getLogRecordFactory()
_handler: logging.Handler | None = None


def canonical_request_id(value: object) -> str | None:
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return value if parsed.version == 4 and str(parsed) == value else None


def current_request_id() -> str:
    return _request_id.get() or str(uuid4())


@contextmanager
def request_context() -> Iterator[str]:
    # Always server-generated: a client cannot spoof correlation or inject a log.
    value = str(uuid4())
    token = _request_id.set(value)
    try:
        yield value
    finally:
        _request_id.reset(token)


def register_routes(paths: Iterable[str]) -> None:
    global _routes
    _routes = frozenset(paths)


def _sanitize(record: logging.LogRecord) -> None:
    if isinstance(record.msg, Event):
        event = record.msg
    elif record.name.startswith("aiogram"):
        event = Event.TELEGRAM
    elif record.name.startswith(("sqlalchemy", "psycopg")):
        event = Event.DATABASE
    else:
        event = Event.LIBRARY
    record.msg = event
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    record.name = "skinulis"
    record.__dict__["correlation_id"] = _request_id.get()


def _record(*args: object, **kwargs: object) -> logging.LogRecord:
    record = _original_factory(*args, **kwargs)
    _sanitize(record)
    return record


class JsonFormatter(logging.Formatter):
    def __init__(self, service: Literal["api", "bot"]) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        # Covers manually constructed records as well as configured stdlib logging.
        correlation = record.__dict__.get("correlation_id", _request_id.get())
        _sanitize(record)
        level = {
            logging.DEBUG: "debug",
            logging.INFO: "info",
            logging.WARNING: "warning",
            logging.ERROR: "error",
            logging.CRITICAL: "critical",
        }.get(record.levelno, "warning")
        value: dict[str, object] = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": level,
            "service": self.service,
            "event": str(record.msg),
            "request_id": canonical_request_id(correlation),
        }
        fields = record.__dict__.get("safe_fields")
        if type(fields) is Fields:
            if canonical_request_id(fields.request_id):
                value["request_id"] = fields.request_id
            if type(fields.status) is int and 100 <= fields.status <= 599:
                value["status"] = fields.status
            if isinstance(fields.method, str) and fields.method in {
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "HEAD",
                "OPTIONS",
            }:
                value["method"] = fields.method
            if isinstance(fields.route, str) and fields.route in _routes:
                value["route"] = fields.route
            if (
                type(fields.duration_ms) is int
                and 0 <= fields.duration_ms <= 86_400_000
            ):
                value["duration_ms"] = fields.duration_ms
            if isinstance(fields.outcome, Outcome):
                value["outcome"] = fields.outcome.value
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


class StdoutHandler(logging.StreamHandler[TextIO]):
    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


def configure_logging(service: Literal["api", "bot"], level: str = "INFO") -> None:
    global _handler
    logging.setLogRecordFactory(_record)
    logging.captureWarnings(True)
    root = logging.getLogger()
    if _handler is not None:
        root.removeHandler(_handler)
    # Preserve embedding/test capture handlers; remove ordinary text stdout/stderr.
    for existing in root.handlers[:]:
        if type(existing) is logging.StreamHandler:
            root.removeHandler(existing)
    handler = StdoutHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root.addHandler(handler)
    _handler = handler
    root.setLevel(level)
    application = logging.getLogger("skinulis")
    application.disabled = False
    application.setLevel(logging.NOTSET)
    application.propagate = True
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    for name in ("httpx", "httpcore", "sqlalchemy", "psycopg", "aiogram"):
        logging.getLogger(name).setLevel(logging.WARNING)


def emit(
    event: Event, *, level: int = logging.INFO, fields: Fields | None = None
) -> None:
    logging.getLogger("skinulis").log(level, event, extra={"safe_fields": fields})
