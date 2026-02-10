from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD
from database.models import SubscriptionType
from bot.keyboards.main_kb import get_profile_kb
from bot.utils.helpers import (
    PROFILE_TEXT,
    format_subscription_name,
    format_date,
    is_subscription_active,
    days_until_expiry,
)

router = Router()


@router.message(F.text == "👤 Профиль")
@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession, bot: Bot):
    """Профиль пользователя"""
    user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Нажмите /start для начала работы.")
        return

    # Формируем блок подписки
    if is_subscription_active(user):
        days = days_until_expiry(user)
        sub_info = f"✅ Подписка активна (осталось {days} дн.)"
    elif user.subscription_type != SubscriptionType.FREE:
        sub_info = "⚠️ Подписка истекла. Продлите для сохранения доступа."
    else:
        sub_info = "💡 Улучшите тариф для безлимитных проверок!"

    text = PROFILE_TEXT.format(
        telegram_id=user.telegram_id,
        full_name=user.full_name or "—",
        plan=format_subscription_name(user.subscription_type),
        expires=format_date(user.subscription_expires),
        checks_today=user.checks_today,
        total_checks=user.total_checks,
        referral_code=user.referral_code or "—",
        referral_earnings=user.referral_earnings,
        subscription_info=sub_info,
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_profile_kb(user.subscription_type),
    )


@router.callback_query(F.data == "referral:info")
async def referral_info(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
):
    """Реферальная программа"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    bot_info = await bot.get_me()
    ref_link = (
        f"https://t.me/{bot_info.username}?start=ref_{user.referral_code}"
    )

    await callback.message.edit_text(
        "🔗 <b>Реферальная программа</b>\n\n"
        "Приглашайте друзей и получайте бонусы!\n\n"
        f"📎 Ваша ссылка:\n<code>{ref_link}</code>\n\n"
        "💰 <b>Награды:</b>\n"
        "├ За каждого приглашённого: +1 бесплатная проверка\n"
        "├ Друг оформил Premium: вы получаете 100₽\n"
        "└ 10+ рефералов: бесплатный месяц Premium\n\n"
        f"👥 Приглашено: скоро\n"
        f"💰 Заработано: {user.referral_earnings}₽",
        parse_mode="HTML",
    )
    await callback.answer()