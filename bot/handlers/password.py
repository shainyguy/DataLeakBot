"""
Обработчики проверки паролей.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD, CheckHistoryCRUD
from database.models import CheckType
from bot.states.check_states import PasswordStates
from bot.keyboards.main_kb import get_cancel_kb
from bot.keyboards.check_kb import get_password_result_kb
from bot.services.password_checker import (
    PasswordCheckerService,
    PasswordFormatter,
)
from bot.services.gigachat_service import GigaChatService
from bot.utils.helpers import is_subscription_active

router = Router()

password_checker = PasswordCheckerService()
gigachat_service = GigaChatService()


@router.message(F.text == "🔑 Проверить пароль")
@router.message(Command("password"))
@router.callback_query(F.data == "password:new")
async def start_password_check(
    event: Message | CallbackQuery, state: FSMContext
):
    """Начало проверки пароля"""
    await state.set_state(PasswordStates.waiting_for_password)

    text = (
        "🔑 <b>Проверка пароля</b>\n\n"
        "Введите пароль для проверки:\n\n"
        "🔒 <b>Безопасность:</b>\n"
        "• Пароль НЕ сохраняется\n"
        "• Используется k-anonymity (HIBP)\n"
        "• На сервер отправляются только первые "
        "5 символов SHA-1 хеша\n\n"
        "⚠️ <i>Рекомендуем удалить сообщение "
        "с паролем после проверки</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_cancel_kb(),
        )
        await event.answer()
    else:
        await event.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_cancel_kb(),
        )


@router.message(PasswordStates.waiting_for_password)
async def process_password_check(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Обработка введённого пароля"""
    password = message.text

    if not password or len(password) < 1:
        await message.answer(
            "❌ Введите пароль для проверки.",
            reply_markup=get_cancel_kb(),
        )
        return

    user = await UserCRUD.get_by_telegram_id(
        session, message.from_user.id
    )
    if not user:
        await message.answer("Нажмите /start.")
        await state.clear()
        return

    # Пытаемся удалить сообщение с паролем
    try:
        await message.delete()
    except Exception:
        pass  # Нет прав на удаление

    processing_msg = await message.answer(
        "🔑 <b>Анализирую пароль...</b>\n"
        "⏳ Проверка по базам утечек...",
        parse_mode="HTML",
    )

    # Проверяем пароль
    result = await password_checker.check_password(password)

    # Сохраняем в историю (без самого пароля!)
    await CheckHistoryCRUD.add(
        session=session,
        user_id=user.id,
        check_type=CheckType.PASSWORD,
        query_value="[PASSWORD_CHECK]",
        breaches_found=1 if result.is_compromised else 0,
        result_data={
            "score": result.score,
            "strength": result.strength,
            "is_compromised": result.is_compromised,
            "times_seen": result.times_seen,
            "length": result.length,
            "entropy": result.entropy_bits,
        },
    )

    # Сохраняем результат для ИИ-советов
    await state.update_data(
        password_result={
            "score": result.score,
            "strength": result.strength,
            "is_compromised": result.is_compromised,
            "warnings": result.warnings,
        }
    )
    await state.clear()

    # Форматируем ответ
    is_premium = is_subscription_active(user)
    text = PasswordFormatter.format_result(result)

    # ИИ-совет для Premium (автоматически)
    if is_premium and (result.score < 60 or result.is_compromised):
        ai_advice = await gigachat_service.get_password_advice(
            score=result.score,
            strength=result.strength,
            is_compromised=result.is_compromised,
            warnings=result.warnings,
        )
        if ai_advice:
            text += ai_advice

    await processing_msg.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_password_result_kb(is_premium=is_premium),
    )


@router.callback_query(F.data == "ai:password_advice")
async def ai_password_advice(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """ИИ-совет по паролю"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Доступно для Premium", show_alert=True
        )
        return

    data = await state.get_data()
    pwd_result = data.get("password_result")

    if not pwd_result:
        await callback.answer(
            "Сначала проверьте пароль", show_alert=True
        )
        return

    await callback.answer("🤖 Генерирую совет...")

    ai_text = await gigachat_service.get_password_advice(
        score=pwd_result["score"],
        strength=pwd_result["strength"],
        is_compromised=pwd_result["is_compromised"],
        warnings=pwd_result.get("warnings", []),
    )

    if ai_text:
        await callback.message.answer(
            ai_text,
            parse_mode="HTML",
        )
    else:
        await callback.answer(
            "ИИ временно недоступен", show_alert=True
        )


# Отмена
@router.callback_query(
    F.data == "cancel",
    PasswordStates.waiting_for_password,
)
async def cancel_password(
    callback: CallbackQuery, state: FSMContext
):
    await state.clear()
    await callback.message.edit_text("❌ Проверка пароля отменена.")
    await callback.answer()