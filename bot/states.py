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


class ExpenseFlow(StatesGroup):
    mode = State()
    draft = State()
    title = State()
    amount = State()
    participants = State()
    share = State()
    item_title = State()
    item_amount = State()
    preview = State()
    edit_confirm = State()
    delete_confirm = State()
    post_uncertain = State()
    put_uncertain = State()
    delete_uncertain = State()
    busy = State()
