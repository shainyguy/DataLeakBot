"""
Семейный мониторинг (Premium).
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD, FamilyCRUD
from database.models import SubscriptionType
from bot.keyboards.monitoring_kb import get_family_menu_kb
from bot.keyboards.main_kb import get_cancel_kb
from bot.services.leak_checker import LeakCheckerService, LeakFormatter
from bot.utils.helpers import (
    validate_email,
    is_subscription_active,
    format_date,
)

router = Router()
leak_checker = LeakCheckerService()


class FamilyStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_email = State()
    waiting_for_phone = State()


# ─── Меню семьи ──────────────────────────────────────────

@router.callback_query(F.data == "family:menu")
async def family_menu(
    callback: CallbackQuery, session: AsyncSession
):
    """Меню семейного мониторинга"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Нужна подписка Premium", show_alert=True
        )
        return

    members = await FamilyCRUD.get_members(session, user.id)

    max_members = (
        FamilyCRUD.MAX_FAMILY_BUSINESS
        if user.subscription_type == SubscriptionType.BUSINESS
        else FamilyCRUD.MAX_FAMILY_MEMBERS
    )

    text = (
        f"👨‍👩‍👧 <b>Семейный мониторинг</b>\n\n"
        f"Защитите близких от утечек данных!\n\n"
        f"👥 Членов семьи: {len(members)}/{max_members}\n\n"
    )

    if members:
        for m in members:
            breach = (
                f"⚠️ {m.breaches_found}"
                if m.breaches_found > 0
                else "✅"
            )
            text += (
                f"├ 👤 {m.name} — {breach}\n"
                f"│  📧 {m.email or '—'}\n"
            )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_family_menu_kb(
            has_members=len(members) > 0
        ),
    )
    await callback.answer()


# ─── Добавление члена семьи ──────────────────────────────

@router.callback_query(F.data == "family:add")
async def family_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Начало добавления члена семьи"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Нужна подписка", show_alert=True
        )
        return

    max_members = (
        FamilyCRUD.MAX_FAMILY_BUSINESS
        if user.subscription_type == SubscriptionType.BUSINESS
        else FamilyCRUD.MAX_FAMILY_MEMBERS
    )
    current = await FamilyCRUD.count_members(
        session, user.id
    )

    if current >= max_members:
        await callback.answer(
            f"Лимит: {max_members} человек",
            show_alert=True,
        )
        return

    await state.set_state(FamilyStates.waiting_for_name)
    await callback.message.edit_text(
        "👤 <b>Добавление члена семьи</b>\n\n"
        "Введите имя:",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )
    await callback.answer()


@router.message(FamilyStates.waiting_for_name)
async def family_add_name(
    message: Message, state: FSMContext
):
    """Получаем имя"""
    name = message.text.strip()[:100]
    await state.update_data(family_name=name)
    await state.set_state(FamilyStates.waiting_for_email)
    await message.answer(
        f"👤 Имя: <b>{name}</b>\n\n"
        "Теперь введите email (или «-» чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )


@router.message(FamilyStates.waiting_for_email)
async def family_add_email(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Получаем email и создаём запись"""
    email_text = message.text.strip()
    data = await state.get_data()
    name = data.get("family_name", "Unknown")

    email = None
    if email_text != "-":
        if validate_email(email_text):
            email = email_text.lower()
        else:
            await message.answer(
                "❌ Некорректный email. "
                "Попробуйте снова или «-»:",
                reply_markup=get_cancel_kb(),
            )
            return

    user = await UserCRUD.get_by_telegram_id(
        session, message.from_user.id
    )
    if not user:
        await state.clear()
        return

    member = await FamilyCRUD.add_member(
        session, user.id, name, email=email
    )
    await state.clear()

    if member:
        await message.answer(
            f"✅ <b>Член семьи добавлен!</b>\n\n"
            f"👤 {name}\n"
            f"📧 {email or 'не указан'}\n\n"
            f"Email будет проверяться на утечки.",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Ошибка добавления.")


# ─── Проверка всей семьи ─────────────────────────────────

@router.callback_query(F.data == "family:check_all")
async def family_check_all(
    callback: CallbackQuery, session: AsyncSession
):
    """Проверить всех членов семьи"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    members = await FamilyCRUD.get_members(session, user.id)
    if not members:
        await callback.answer(
            "Нет членов семьи", show_alert=True
        )
        return

    await callback.answer("🔍 Проверяю...")
    await callback.message.edit_text(
        f"🔍 Проверяю {len(members)} членов семьи...",
        parse_mode="HTML",
    )

    results = []
    for member in members:
        if member.email:
            result = await leak_checker.check_email(
                member.email
            )
            results.append((member, result))

    # Формируем отчёт
    lines = ["👨‍👩‍👧 <b>Отчёт по семье</b>\n"]

    total_breaches = 0
    for member, result in results:
        emoji = "🚨" if result.is_compromised else "✅"
        lines.append(
            f"{emoji} <b>{member.name}</b> — "
            f"{result.total_breaches} утечек"
        )
        total_breaches += result.total_breaches

    lines.append(f"\n📊 Всего утечек: {total_breaches}")

    if total_breaches > 0:
        lines.append(
            "\n⚠️ Рекомендуем сменить пароли "
            "для скомпрометированных аккаунтов."
        )

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ─── Список семьи ────────────────────────────────────────

@router.callback_query(F.data == "family:list")
async def family_list(
    callback: CallbackQuery, session: AsyncSession
):
    """Список членов семьи"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    members = await FamilyCRUD.get_members(session, user.id)

    if not members:
        await callback.answer(
            "Нет членов семьи", show_alert=True
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    for member in members:
        builder.row(
            InlineKeyboardButton(
                text=f"👤 {member.name}",
                callback_data=f"family:detail:{member.id}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"family:remove:{member.id}",
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="family:menu",
        )
    )

    await callback.message.edit_text(
        "👨‍👩‍👧 <b>Члены семьи:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("family:remove:"))
async def family_remove(
    callback: CallbackQuery, session: AsyncSession
):
    """Удалить члена семьи"""
    member_id = int(callback.data.split(":")[2])

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    removed = await FamilyCRUD.remove_member(
        session, user.id, member_id
    )

    if removed:
        await callback.answer(
            "🗑 Удалено", show_alert=True
        )
    else:
        await callback.answer(
            "Не найдено", show_alert=True
        )


# ─── Отмена FSM ──────────────────────────────────────────

@router.callback_query(
    F.data == "cancel",
    FamilyStates.waiting_for_name,
)
@router.callback_query(
    F.data == "cancel",
    FamilyStates.waiting_for_email,
)
async def cancel_family(
    callback: CallbackQuery, state: FSMContext
):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()