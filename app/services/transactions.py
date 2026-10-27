"""Write services own the whole request transaction, including auth's autobegin."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def write_transaction(session: Session) -> Iterator[None]:
    # Auth has already SELECTed in this same Session. Do not nest session.begin().
    # A service is one top-level operation, never called inside another write service.
    try:
        yield
        session.commit()
    except Exception:
        session.rollback()
        raise
