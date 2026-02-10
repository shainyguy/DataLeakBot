from aiogram.fsm.state import State, StatesGroup


class CheckStates(StatesGroup):
    """Состояния для проверки утечек"""
    waiting_for_email = State()
    waiting_for_phone = State()
    waiting_for_username = State()
    waiting_for_any = State()


class PasswordStates(StatesGroup):
    """Состояния для проверки пароля"""
    waiting_for_password = State()