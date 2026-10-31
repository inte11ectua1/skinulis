"""T-08 durable at-most-once permission. No delivery or financial state changes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.identity_tokens import utc_now
from app.models import GroupMember, Settlement, User
from app.schemas.settlements import NotificationClaim
from app.services.groups import require_member
from app.services.transactions import write_transaction


def claim_notification(
    session: Session, settlement_id: int, actor_id: int
) -> NotificationClaim | None:
    with write_transaction(session):
        with session.no_autoflush:
            group_id = session.scalar(
                select(Settlement.group_id).where(Settlement.id == settlement_id)
            )
            if group_id is None:
                raise ApiError(404, "settlement_not_found", "Settlement not found")
            try:
                require_member(session, group_id, actor_id, lock=True)
            except ApiError as error:
                if error.status == 404:
                    raise ApiError(
                        404, "settlement_not_found", "Settlement not found"
                    ) from None
                raise
            row = session.scalar(
                select(Settlement)
                .where(Settlement.id == settlement_id, Settlement.group_id == group_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        if (
            row is None
            or row.sender_id != actor_id
            or session.get(GroupMember, (group_id, row.receiver_id)) is None
        ):
            raise ApiError(404, "settlement_not_found", "Settlement not found")
        if row.status != "pending" or row.notification_claimed_at is not None:
            return None
        telegram_id = session.scalar(
            select(User.telegram_id).where(User.id == row.receiver_id)
        )
        # Validate the server binding before committing/returning a permission.
        result = (
            None
            if telegram_id is None
            else NotificationClaim(recipient_telegram_id=telegram_id)
        )
        row.notification_claimed_at = utc_now()
        session.flush()
        return result
