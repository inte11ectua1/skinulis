from aiogram.fsm.state import State, StatesGroup


class Navigation(StatesGroup):
    # Navigation only: this state is not evidence of authentication or membership.
    menu = State()
