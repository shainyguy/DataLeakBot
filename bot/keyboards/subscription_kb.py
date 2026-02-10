from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import settings


def get_subscription_plans_kb() -> InlineKeyboardMarkup:
    """Выбор тарифного плана"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"⭐ Premium — {settings.premium_price}₽/мес",
            callback_data="subscribe:premium",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🏢 Business — {settings.business_price}₽/мес",
            callback_data="subscribe:business",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад", callback_data="back:menu"
        )
    )
    return builder.as_markup()


def get_payment_kb(payment_url: str, payment_id: str) -> InlineKeyboardMarkup:
    """Кнопка оплаты"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💳 Оплатить",
            url=payment_url,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✅ Я оплатил",
            callback_data=f"check_payment:{payment_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="cancel_payment",
        )
    )
    return builder.as_markup()


def get_manage_subscription_kb() -> InlineKeyboardMarkup:
    """Управление подпиской"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔄 Продлить подписку",
            callback_data="subscription:renew",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Сменить тариф",
            callback_data="subscription:show",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад", callback_data="back:menu"
        )
    )
    return builder.as_markup()