"""Сессия на запрос; транзакцией записи владеет будущий service (session.begin)."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(
            settings.get_database_url(),
            pool_pre_ping=True,
            pool_timeout=3,
            hide_parameters=True,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def close(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    with database.sessions() as session:
        # No implicit commit: session.close rolls back uncommitted work.
        yield session
