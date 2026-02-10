from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD
from bot.keyboards.main_kb import get_main_menu_kb
from bot.utils.helpers import (
    WELCOME_TEXT,
    format_subscription_name,
    format_date,
)

router = Router()


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    command: CommandObject | None = None,
):
    """Обработчик /start с поддержкой deep linking (рефералы)"""
    referrer_id = None

    # Обработка реферальной ссылки /start ref_CODE
    if command and command.args:
        args = command.args
        if args.startswith("ref_"):
            ref_code = args[4:]
            referrer = await UserCRUD.get_by_referral_code(session, ref_code)
            if referrer and referrer.telegram_id != message.from_user.id:
                referrer_id = referrer.telegram_id

    user, created = await UserCRUD.get_or_create(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name or "",
        referred_by=referrer_id,
    )

    welcome = WELCOME_TEXT.format(
        plan=format_subscription_name(user.subscription_type),
        reg_date=format_date(user.created_at),
    )

    if created:
        welcome = "🎉 <b>Добро пожаловать!</b>\n" + welcome
        if referrer_id:
            welcome += "\n🔗 Вы пришли по реферальной ссылке!"

    await message.answer(
        welcome,
        parse_mode="HTML",
        reply_markup=get_main_menu_kb(),
    )