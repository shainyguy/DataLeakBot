from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD
from bot.keyboards.main_kb import get_main_menu_kb, get_check_type_kb
from bot.utils.helpers import WELCOME_TEXT, format_subscription_name, format_date

router = Router()


@router.message(Command("menu"))
@router.message(F.text == "🔙 Меню")
async def cmd_menu(message: Message, session: AsyncSession):
    """Главное меню"""
    user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Нажмите /start для начала работы.")
        return

    text = WELCOME_TEXT.format(
        plan=format_subscription_name(user.subscription_type),
        reg_date=format_date(user.created_at),
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_main_menu_kb(),
    )


@router.callback_query(F.data == "back:menu")
async def callback_back_menu(callback: CallbackQuery, session: AsyncSession):
    """Возврат в меню через inline-кнопку"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Нажмите /start")
        return

    text = WELCOME_TEXT.format(
        plan=format_subscription_name(user.subscription_type),
        reg_date=format_date(user.created_at),
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text == "🔍 Проверить данные")
async def check_data_menu(message: Message, session: AsyncSession):
    """Меню проверки данных"""
    await message.answer(
        "🔍 <b>Проверка данных на утечки</b>\n\n"
        "Выберите, что хотите проверить:",
        parse_mode="HTML",
        reply_markup=get_check_type_kb(),
    )


@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    """Помощь"""
    await message.answer(
        "🛡 <b>DataLeakBot — Справка</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start — Запуск бота\n"
        "/menu — Главное меню\n"
        "/check — Проверить данные\n"
        "/password — Проверить пароль\n"
        "/monitor — Мониторинг\n"
        "/profile — Ваш профиль\n"
        "/subscribe — Подписка\n"
        "/help — Эта справка\n\n"
        "<b>Как это работает?</b>\n"
        "Мы проверяем ваш email/телефон по базам "
        "известных утечек данных. Если ваши данные "
        "были скомпрометированы, мы покажем:\n"
        "• В каких сервисах произошла утечка\n"
        "• Какие данные попали в открытый доступ\n"
        "• Рекомендации по защите\n\n"
        "🔒 Мы НЕ храним ваши пароли и личные данные.\n"
        "Все запросы шифруются.\n\n"
        "📩 Поддержка: @YourSupportBot",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery):
    """Отмена действия"""
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer()