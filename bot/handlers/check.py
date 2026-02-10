"""
Обработчики проверки утечек: email, телефон, username.
"""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD, CheckHistoryCRUD
from database.models import SubscriptionType, CheckType
from bot.states.check_states import CheckStates
from bot.keyboards.main_kb import get_check_type_kb, get_cancel_kb
from bot.keyboards.check_kb import (
    get_check_result_kb,
    get_breach_navigation_kb,
)
from bot.services.leak_checker import (
    LeakCheckerService,
    LeakFormatter,
    LeakCheckResult,
)
from bot.services.gigachat_service import GigaChatService
from bot.utils.helpers import (
    validate_email,
    validate_phone,
    normalize_phone,
    is_subscription_active,
)

router = Router()

# Инициализация сервисов
leak_checker = LeakCheckerService()
gigachat_service = GigaChatService()


# ─── Точки входа ─────────────────────────────────────────

@router.message(Command("check"))
@router.callback_query(F.data == "check:new")
async def start_check(
    event: Message | CallbackQuery,
    session: AsyncSession,
):
    """Начало проверки — выбор типа"""
    text = (
        "🔍 <b>Проверка данных на утечки</b>\n\n"
        "Выберите, что хотите проверить:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_check_type_kb(),
        )
        await event.answer()
    else:
        await event.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_check_type_kb(),
        )


# ─── Выбор типа проверки ─────────────────────────────────

@router.callback_query(F.data == "check:email")
async def select_email_check(
    callback: CallbackQuery, state: FSMContext
):
    """Выбрана проверка email"""
    await state.set_state(CheckStates.waiting_for_email)
    await callback.message.edit_text(
        "📧 <b>Проверка Email</b>\n\n"
        "Введите email адрес для проверки:\n\n"
        "<i>Пример: user@mail.ru</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "check:phone")
async def select_phone_check(
    callback: CallbackQuery, state: FSMContext
):
    """Выбрана проверка телефона"""
    await state.set_state(CheckStates.waiting_for_phone)
    await callback.message.edit_text(
        "📱 <b>Проверка телефона</b>\n\n"
        "Введите номер телефона:\n\n"
        "<i>Пример: +79991234567</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "check:username")
async def select_username_check(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Выбрана проверка username (Premium)"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or (
        user.subscription_type == SubscriptionType.FREE
        and not is_subscription_active(user)
    ):
        await callback.answer(
            "👤 Проверка username доступна в Premium тарифе",
            show_alert=True,
        )
        return

    await state.set_state(CheckStates.waiting_for_username)
    await callback.message.edit_text(
        "👤 <b>Проверка имени пользователя</b>\n\n"
        "Введите username для проверки:\n\n"
        "<i>Пример: ivan_petrov</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )
    await callback.answer()


# ─── Обработка ввода ─────────────────────────────────────

@router.message(CheckStates.waiting_for_email)
async def process_email_check(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Обработка введённого email"""
    email = message.text.strip().lower()

    if not validate_email(email):
        await message.answer(
            "❌ Некорректный email адрес.\n"
            "Введите email в формате: user@domain.com",
            reply_markup=get_cancel_kb(),
        )
        return

    user = await UserCRUD.get_by_telegram_id(
        session, message.from_user.id
    )
    if not user:
        await message.answer("Нажмите /start для начала работы.")
        await state.clear()
        return

    # Проверяем лимит
    can_check = await UserCRUD.can_check(session, user)
    if not can_check:
        await message.answer(
            "⏳ <b>Лимит проверок исчерпан</b>\n\n"
            "Бесплатный тариф: 1 проверка в день.\n\n"
            "💎 Оформите Premium для безлимитных проверок!",
            parse_mode="HTML",
            reply_markup=get_cancel_kb(),
        )
        await state.clear()
        return

    # Выполняем проверку
    processing_msg = await message.answer(
        "🔍 <b>Проверяю...</b>\n\n"
        "⏳ Поиск по базам утечек...\n"
        "Это может занять несколько секунд.",
        parse_mode="HTML",
    )

    result = await leak_checker.check_email(email)

    # Сохраняем в историю
    await CheckHistoryCRUD.add(
        session=session,
        user_id=user.id,
        check_type=CheckType.EMAIL,
        query_value=email,
        breaches_found=result.total_breaches,
        result_data=result.to_dict(),
    )

    # Увеличиваем счётчик
    await UserCRUD.increment_check(session, user)

    # Сохраняем результат в FSM для дальнейшей навигации
    await state.update_data(
        last_result=result.to_dict(),
        last_query=email,
        last_query_type="email",
    )
    await state.clear()

    # Формируем ответ
    is_premium = is_subscription_active(user)

    # Основная информация
    main_text = LeakFormatter.format_result(result)

    # Детали утечек (первые 3)
    if result.breaches:
        for i, breach in enumerate(result.breaches[:3], 1):
            main_text += LeakFormatter.format_breach(breach, i)

        if len(result.breaches) > 3:
            main_text += (
                f"\n\n📄 <i>Показаны 3 из "
                f"{result.total_breaches} утечек. "
                f"Нажмите кнопку ниже для просмотра всех.</i>"
            )

    # Рекомендации
    recommendations = LeakFormatter.format_recommendations(result)
    if recommendations:
        main_text += "\n" + recommendations

    try:
        await processing_msg.edit_text(
            main_text,
            parse_mode="HTML",
            reply_markup=get_check_result_kb(
                has_breaches=result.is_compromised,
                is_premium=is_premium,
            ),
        )
    except Exception:
        # Текст слишком длинный — разбиваем
        await processing_msg.edit_text(
            LeakFormatter.format_result(result),
            parse_mode="HTML",
        )
        if result.breaches:
            breach_text = ""
            for i, breach in enumerate(result.breaches[:5], 1):
                breach_text += LeakFormatter.format_breach(breach, i)
            await message.answer(
                breach_text + "\n" + recommendations,
                parse_mode="HTML",
                reply_markup=get_check_result_kb(
                    has_breaches=result.is_compromised,
                    is_premium=is_premium,
                ),
            )


@router.message(CheckStates.waiting_for_phone)
async def process_phone_check(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Обработка введённого телефона"""
    phone_raw = message.text.strip()

    if not validate_phone(phone_raw):
        await message.answer(
            "❌ Некорректный номер телефона.\n"
            "Введите в формате: +79991234567 или 89991234567",
            reply_markup=get_cancel_kb(),
        )
        return

    phone = normalize_phone(phone_raw)

    user = await UserCRUD.get_by_telegram_id(
        session, message.from_user.id
    )
    if not user:
        await message.answer("Нажмите /start.")
        await state.clear()
        return

    can_check = await UserCRUD.can_check(session, user)
    if not can_check:
        await message.answer(
            "⏳ Лимит проверок исчерпан. "
            "Оформите Premium для безлимита!",
            parse_mode="HTML",
        )
        await state.clear()
        return

    processing_msg = await message.answer(
        "🔍 <b>Проверяю номер...</b>\n⏳ Поиск по базам...",
        parse_mode="HTML",
    )

    result = await leak_checker.check_phone(phone)

    await CheckHistoryCRUD.add(
        session=session,
        user_id=user.id,
        check_type=CheckType.PHONE,
        query_value=phone,
        breaches_found=result.total_breaches,
        result_data=result.to_dict(),
    )
    await UserCRUD.increment_check(session, user)

    await state.update_data(
        last_result=result.to_dict(),
        last_query=phone,
        last_query_type="phone",
    )
    await state.clear()

    is_premium = is_subscription_active(user)
    main_text = LeakFormatter.format_result(result)

    if result.breaches:
        for i, breach in enumerate(result.breaches[:3], 1):
            main_text += LeakFormatter.format_breach(breach, i)

    recommendations = LeakFormatter.format_recommendations(result)
    if recommendations:
        main_text += "\n" + recommendations

    await processing_msg.edit_text(
        main_text,
        parse_mode="HTML",
        reply_markup=get_check_result_kb(
            has_breaches=result.is_compromised,
            is_premium=is_premium,
        ),
    )


@router.message(CheckStates.waiting_for_username)
async def process_username_check(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Обработка введённого username"""
    username = message.text.strip()

    if len(username) < 2 or len(username) > 100:
        await message.answer(
            "❌ Некорректное имя пользователя.",
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

    processing_msg = await message.answer(
        "🔍 <b>Проверяю username...</b>\n⏳ Поиск...",
        parse_mode="HTML",
    )

    result = await leak_checker.check_username(username)

    await CheckHistoryCRUD.add(
        session=session,
        user_id=user.id,
        check_type=CheckType.USERNAME,
        query_value=username,
        breaches_found=result.total_breaches,
        result_data=result.to_dict(),
    )
    await UserCRUD.increment_check(session, user)

    await state.clear()

    is_premium = is_subscription_active(user)
    main_text = LeakFormatter.format_result(result)

    await processing_msg.edit_text(
        main_text,
        parse_mode="HTML",
        reply_markup=get_check_result_kb(
            has_breaches=result.is_compromised,
            is_premium=is_premium,
        ),
    )


# ─── ИИ-рекомендации ─────────────────────────────────────

@router.callback_query(F.data == "ai:recommendations")
async def ai_recommendations(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """ИИ-рекомендации по утечкам (Premium)"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Доступно только для Premium", show_alert=True
        )
        return

    data = await state.get_data()
    last_result = data.get("last_result")
    last_query = data.get("last_query", "")

    if not last_result:
        await callback.answer(
            "Сначала выполните проверку", show_alert=True
        )
        return

    await callback.answer("🤖 Генерирую рекомендации...")

    processing = await callback.message.answer(
        "🤖 <b>ИИ анализирует ваши утечки...</b>\n"
        "⏳ Это может занять до 15 секунд.",
        parse_mode="HTML",
    )

    breaches = last_result.get("breaches", [])
    email_domain = ""
    if "@" in last_query:
        email_domain = last_query.split("@")[1]

    ai_text = await gigachat_service.get_leak_recommendations(
        breaches=breaches,
        email_domain=email_domain,
    )

    await processing.edit_text(
        ai_text,
        parse_mode="HTML",
    )


# ─── Отмена FSM ──────────────────────────────────────────

@router.callback_query(
    F.data == "cancel",
    CheckStates.waiting_for_email,
)
@router.callback_query(
    F.data == "cancel",
    CheckStates.waiting_for_phone,
)
@router.callback_query(
    F.data == "cancel",
    CheckStates.waiting_for_username,
)
async def cancel_check(callback: CallbackQuery, state: FSMContext):
    """Отмена проверки"""
    await state.clear()
    await callback.message.edit_text("❌ Проверка отменена.")
    await callback.answer()