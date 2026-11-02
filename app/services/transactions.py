"""Write services own the endpoint transaction; authentication has its own scope."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def write_transaction(session: Session) -> Iterator[None]:
    # Preliminary service reads may have autobegun. Do not nest session.begin().
    # A service is one top-level operation, never called inside another write service.
    try:
        yield
        session.commit()
    except Exception:
        session.rollback()
        raise
