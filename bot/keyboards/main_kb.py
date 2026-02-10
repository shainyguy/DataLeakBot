from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from database.models import SubscriptionType


def get_main_menu_kb() -> ReplyKeyboardMarkup:
    """Основная клавиатура бота"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🔍 Проверить данные"),
        KeyboardButton(text="🔑 Проверить пароль"),
    )
    builder.row(
        KeyboardButton(text="📊 Мониторинг"),
        KeyboardButton(text="📋 История"),
    )
    builder.row(
        KeyboardButton(text="👤 Профиль"),
        KeyboardButton(text="💎 Подписка"),
    )
    builder.row(
        KeyboardButton(text="ℹ️ Помощь"),
    )
    return builder.as_markup(resize_keyboard=True)


def get_check_type_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа проверки"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📧 Email", callback_data="check:email"
        ),
        InlineKeyboardButton(
            text="📱 Телефон", callback_data="check:phone"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 Имя пользователя", callback_data="check:username"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔑 Проверить пароль", callback_data="password:new"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад", callback_data="back:menu"
        ),
    )
    return builder.as_markup()


def get_back_kb(
    callback_data: str = "back:menu",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад", callback_data=callback_data
        )
    )
    return builder.as_markup()


def get_profile_kb(
    sub_type: SubscriptionType,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if sub_type == SubscriptionType.FREE:
        builder.row(
            InlineKeyboardButton(
                text="⭐ Улучшить тариф",
                callback_data="subscription:show",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="📋 История проверок",
            callback_data="history:show",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔗 Реферальная программа",
            callback_data="referral:info",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Меню", callback_data="back:menu"
        )
    )
    return builder.as_markup()


def get_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена", callback_data="cancel"
        )
    )
    return builder.as_markup()