from aiogram.fsm.state import State, StatesGroup


class Navigation(StatesGroup):
    # Navigation only: this state is not evidence of authentication or membership.
    menu = State()


class Onboarding(StatesGroup):
    choice = State()
    consent = State()
    link_code = State()
    uncertain = State()


class GroupFlow(StatesGroup):
    name = State()
    confirm = State()
    invite_confirm = State()
    invite_uncertain = State()
    revoke_confirm = State()
    join_confirm = State()
    join_uncertain = State()
    busy = State()
