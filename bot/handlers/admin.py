"""
Админ-панель бота.
"""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.crud import UserCRUD, AdminCRUD
from database.models import SubscriptionType
from bot.keyboards.admin_kb import (
    get_admin_menu_kb,
    get_admin_users_kb,
    get_admin_user_actions_kb,
)
from bot.utils.helpers import (
    format_subscription_name,
    format_date,
    is_subscription_active,
)

router = Router()


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_grant_id = State()


# ─── Проверка админа ─────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


# ─── Админ-меню ──────────────────────────────────────────

@router.message(Command("admin"))
@router.callback_query(F.data == "admin:menu")
async def admin_menu(event: Message | CallbackQuery):
    tg_id = event.from_user.id
    if not is_admin(tg_id):
        return

    text = "🔧 <b>Админ-панель DataLeakBot</b>"

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_admin_menu_kb(),
        )
        await event.answer()
    else:
        await event.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_admin_menu_kb(),
        )


# ─── Статистика ──────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    user_stats = await UserCRUD.get_stats(session)
    check_stats = await AdminCRUD.get_check_stats(session)

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        "👥 <b>Пользователи:</b>\n"
        f"├ Всего: {user_stats['total']}\n"
        f"├ ⭐ Premium: {user_stats['premium']}\n"
        f"├ 🏢 Business: {user_stats['business']}\n"
        f"└ 🆕 Сегодня: {user_stats['new_today']}\n\n"
        "🔍 <b>Проверки:</b>\n"
        f"├ Всего: {check_stats['total_checks']}\n"
        f"├ Сегодня: {check_stats['today_checks']}\n"
        f"└ С утечками: {check_stats['checks_with_breaches']}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_admin_menu_kb(),
    )
    await callback.answer()


# ─── Доходы ──────────────────────────────────────────────

@router.callback_query(F.data == "admin:revenue")
async def admin_revenue(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    stats = await AdminCRUD.get_revenue_stats(session)

    text = (
        "💰 <b>Доходы</b>\n\n"
        "📅 <b>Сегодня:</b>\n"
        f"├ Платежей: {stats['today_payments']}\n"
        f"└ Сумма: {stats['today_revenue']}₽\n\n"
        "📆 <b>За месяц:</b>\n"
        f"├ Платежей: {stats['month_payments']}\n"
        f"└ Сумма: {stats['month_revenue']}₽\n\n"
        "📊 <b>За всё время:</b>\n"
        f"├ Платежей: {stats['total_payments']}\n"
        f"└ Сумма: {stats['total_revenue']}₽\n\n"
        f"💵 ARPU: "
        f"{stats['total_revenue'] // max(stats['total_payments'], 1)}₽"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_admin_menu_kb(),
    )
    await callback.answer()


# ─── Пользователи ────────────────────────────────────────

@router.callback_query(F.data == "admin:users")
@router.callback_query(F.data.startswith("admin:users:"))
async def admin_users(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    filter_type = parts[2] if len(parts) > 2 else "all"
    page = int(parts[3]) if len(parts) > 3 else 0

    sub_filter = None
    if filter_type == "premium":
        sub_filter = SubscriptionType.PREMIUM
    elif filter_type == "business":
        sub_filter = SubscriptionType.BUSINESS

    per_page = 10
    total = await AdminCRUD.count_users(session, sub_filter)
    total_pages = max(1, (total + per_page - 1) // per_page)

    users = await AdminCRUD.get_all_users(
        session,
        limit=per_page,
        offset=page * per_page,
        subscription_filter=sub_filter,
    )

    lines = [
        f"👥 <b>Пользователи</b> "
        f"({total} | стр. {page + 1}/{total_pages})\n"
    ]

    for user in users:
        sub = format_subscription_name(user.subscription_type)
        blocked = " 🚫" if user.is_blocked else ""
        lines.append(
            f"├ <code>{user.telegram_id}</code> "
            f"@{user.username or '—'} {sub}{blocked}"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_admin_users_kb(page, total_pages),
    )
    await callback.answer()


# ─── Найти пользователя ──────────────────────────────────

@router.callback_query(F.data == "admin:find_user")
async def admin_find_user_start(
    callback: CallbackQuery, state: FSMContext
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "🔍 Введите Telegram ID пользователя:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id)
async def admin_find_user(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный ID. Введите число:")
        return

    user = await UserCRUD.get_by_telegram_id(session, tg_id)
    await state.clear()

    if not user:
        await message.answer(f"❌ Пользователь {tg_id} не найден.")
        return

    active = "✅ Активна" if is_subscription_active(user) else "❌ Нет"

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"├ 🆔 ID: <code>{user.telegram_id}</code>\n"
        f"├ 👤 @{user.username or '—'}\n"
        f"├ 📛 {user.full_name}\n"
        f"├ 📊 Тариф: "
        f"{format_subscription_name(user.subscription_type)}\n"
        f"├ ⏰ До: {format_date(user.subscription_expires)}\n"
        f"├ 📊 Подписка: {active}\n"
        f"├ 🔍 Проверок: {user.total_checks}\n"
        f"├ 🚫 Блок: {'Да' if user.is_blocked else 'Нет'}\n"
        f"└ 📅 Регистрация: {format_date(user.created_at)}"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_admin_user_actions_kb(
            user.telegram_id, user.is_blocked
        ),
    )


# ─── Блокировка ──────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:block:"))
async def admin_block(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    tg_id = int(callback.data.split(":")[2])
    result = await AdminCRUD.block_user(session, tg_id)

    if result:
        await callback.answer(
            f"🚫 Пользователь {tg_id} заблокирован",
            show_alert=True,
        )
    else:
        await callback.answer("Не найден", show_alert=True)


@router.callback_query(F.data.startswith("admin:unblock:"))
async def admin_unblock(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    tg_id = int(callback.data.split(":")[2])
    result = await AdminCRUD.unblock_user(session, tg_id)

    if result:
        await callback.answer(
            f"✅ Пользователь {tg_id} разблокирован",
            show_alert=True,
        )
    else:
        await callback.answer("Не найден", show_alert=True)


# ─── Выдача подписки ─────────────────────────────────────

@router.callback_query(F.data.startswith("admin:give_prem:"))
async def admin_give_premium(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    tg_id = int(callback.data.split(":")[2])
    result = await AdminCRUD.grant_subscription(
        session, tg_id, SubscriptionType.PREMIUM, days=30
    )

    if result:
        await callback.answer(
            f"⭐ Premium выдан {tg_id} на 30 дней",
            show_alert=True,
        )
    else:
        await callback.answer("Не найден", show_alert=True)


@router.callback_query(F.data.startswith("admin:give_biz:"))
async def admin_give_business(
    callback: CallbackQuery, session: AsyncSession
):
    if not is_admin(callback.from_user.id):
        return

    tg_id = int(callback.data.split(":")[2])
    result = await AdminCRUD.grant_subscription(
        session, tg_id, SubscriptionType.BUSINESS, days=30
    )

    if result:
        await callback.answer(
            f"🏢 Business выдан {tg_id} на 30 дней",
            show_alert=True,
        )
    else:
        await callback.answer("Не найден", show_alert=True)


@router.callback_query(F.data == "admin:grant")
async def admin_grant_start(
    callback: CallbackQuery, state: FSMContext
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_grant_id)
    await callback.message.edit_text(
        "🎁 Введите Telegram ID для выдачи подписки:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_grant_id)
async def admin_grant_process(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный ID.")
        return

    user = await UserCRUD.get_by_telegram_id(session, tg_id)
    await state.clear()

    if not user:
        await message.answer(f"❌ Пользователь {tg_id} не найден.")
        return

    await message.answer(
        f"🎁 Выберите подписку для {tg_id}:",
        parse_mode="HTML",
        reply_markup=get_admin_user_actions_kb(
            tg_id, user.is_blocked
        ),
    )


# ─── Рассылка ────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(
    callback: CallbackQuery, state: FSMContext
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Введите текст сообщения для всех "
        "пользователей.\n\n"
        "Поддерживается HTML-разметка.\n"
        "Отправьте /cancel для отмены.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def admin_broadcast_send(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return

    broadcast_text = message.text or message.caption or ""
    if not broadcast_text:
        await message.answer("❌ Пустое сообщение.")
        return

    await state.clear()
    await message.answer("📤 Начинаю рассылку...")

    # Получаем всех пользователей
    all_users = await AdminCRUD.get_all_users(
        session, limit=100000
    )

    sent = 0
    failed = 0

    for user in all_users:
        if user.is_blocked:
            continue
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=broadcast_text,
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1

        # Антиспам — Telegram ограничивает ~30 msg/sec
        if sent % 25 == 0:
            import asyncio
            await asyncio.sleep(1)

    await message.answer(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибки: {failed}\n"
        f"📊 Всего: {len(all_users)}",
        parse_mode="HTML",
    )