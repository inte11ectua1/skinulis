"""Actor-scoped profile editing; never changes authentication or other accounts."""

from sqlalchemy.orm import Session

from app.models import User
from app.services.transactions import write_transaction


def update_profile(session: Session, user: User, display_name: str) -> User:
    with write_transaction(session):
        user.display_name = display_name
        session.add(user)
        session.flush()
    return user
