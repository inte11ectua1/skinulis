"""Transient L-05 input/recovery context; financial truth always comes from HTTP."""

from typing import Literal
from uuid import UUID

from aiogram.fsm.context import FSMContext
from pydantic import BaseModel, Field

from bot.settlement_dto import Direction, Transition


class SettlementSession(BaseModel):
    group_id: int
    receiver_id: int | None = None
    amount: str = ""
    members: list[int] = Field(default_factory=list)
    frozen: str | None = None
    target_id: int | None = None
    target_key: UUID | None = None
    direction: Direction = "all"
    purpose: Literal["detail", "creation", "review", "reconcile"] = "detail"
    operation: Transition | None = None
    uncertain: Literal["create", "transition"] | None = None
    can_retry: bool = False

    @property
    def recovering(self) -> bool:
        return self.uncertain is not None or (
            self.purpose == "creation" and self.frozen is not None
        )


async def load(state: FSMContext) -> SettlementSession:
    return SettlementSession.model_validate_json(
        (await state.get_data())["settlement_session"]
    )


async def keep(state: FSMContext, session: SettlementSession) -> None:
    await state.update_data(
        settlement_session=session.model_dump_json(), screen=None, actions=[]
    )
