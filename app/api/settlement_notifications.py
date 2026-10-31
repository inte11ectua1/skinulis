"""Internal-only sender claim. A 200 permits one attempt, never promises delivery."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.groups import ERRORS
from app.api.settlements import settlement_headers
from app.api.telegram_dependencies import get_bot_user
from app.core.errors import ApiError
from app.db import get_session
from app.models import User
from app.schemas.groups import PathId
from app.schemas.settlements import NotificationClaim
from app.services.settlement_notifications import claim_notification

router = APIRouter(
    prefix="/internal",
    tags=["settlement notifications"],
    responses=ERRORS,
    dependencies=[Depends(settlement_headers)],
)


async def require_no_body(request: Request) -> None:
    if await request.body():
        raise ApiError(400, "validation_error", "This operation has no request body")


@router.post(
    "/settlements/{settlement_id}/notification-claim",
    response_model=NotificationClaim,
    responses={
        204: {"description": "No permission. Empty response; do not send a message."}
    },
)
def claim(
    settlement_id: PathId,
    response: Response,
    user: Annotated[User, Depends(get_bot_user)],
    session: Annotated[Session, Depends(get_session)],
    no_body: Annotated[None, Depends(require_no_body)],
) -> NotificationClaim | Response:
    """Verified sender only. Commit before send; on 204/error/timeout do not send.

    Recipient comes only from the receiver's server Telegram binding. Retrying a
    committed claim never grants another attempt, including after a lost response.
    """
    result = claim_notification(session, settlement_id, user.id)
    if result is None:
        return Response(status_code=204, headers=dict(response.headers))
    return result
