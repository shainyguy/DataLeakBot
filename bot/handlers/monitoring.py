"""
Обработчики мониторинга и dark web.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import (
    UserCRUD,
    MonitorCRUD,
    DarkWebCRUD,
)
from database.models import SubscriptionType
from bot.keyboards.monitoring_kb import (
    get_monitoring_menu_kb,
    get_monitored_list_kb,
    get_monitor_detail_kb,
    get_darkweb_alerts_kb,
)
from bot.keyboards.main_kb import get_cancel_kb
from bot.services.leak_checker import LeakCheckerService, LeakFormatter
from bot.services.darkweb_service import DarkWebService, DarkWebFormatter
from bot.utils.helpers import (
    validate_email,
    is_subscription_active,
    format_date,
)

router = Router()

leak_checker = LeakCheckerService()
darkweb_service = DarkWebService()


class MonitorStates(StatesGroup):
    waiting_for_email = State()


# ─── Лимиты по тарифу ────────────────────────────────────

def _get_monitor_limit(sub_type: SubscriptionType) -> int:
    limits = {
        SubscriptionType.FREE: 0,
        SubscriptionType.PREMIUM: 5,
        SubscriptionType.BUSINESS: 50,
    }
    return limits.get(sub_type, 0)


# ─── Главное меню мониторинга ─────────────────────────────

@router.message(F.text == "📊 Мониторинг")
@router.message(Command("monitor"))
@router.callback_query(F.data == "monitor:menu")
async def monitoring_menu(
    event: Message | CallbackQuery,
    session: AsyncSession,
):
    """Меню мониторинга"""
    tg_id = event.from_user.id
    user = await UserCRUD.get_by_telegram_id(session, tg_id)

    if not user:
        text = "Нажмите /start для начала."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return

    if not is_subscription_active(user):
        text = (
            "📊 <b>Мониторинг утечек</b>\n\n"
            "🔒 Мониторинг доступен для подписчиков "
            "Premium и Business.\n\n"
            "⭐ <b>Premium (790₽/мес):</b>\n"
            "├ До 5 email на мониторинге\n"
            "├ Уведомления о новых утечках\n"
            "├ Dark Web мониторинг\n"
            "└ Семейный мониторинг\n\n"
            "🏢 <b>Business (1790₽/мес):</b>\n"
            "├ До 50 email\n"
            "└ Корпоративный домен\n\n"
            "Оформите подписку: /subscribe"
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(
                text, parse_mode="HTML"
            )
            await event.answer()
        else:
            await event.answer(text, parse_mode="HTML")
        return

    # Получаем данные мониторинга
    monitored = await MonitorCRUD.get_user_monitored(
        session, user.id
    )
    unread_alerts = await DarkWebCRUD.count_unread(
        session, user.id
    )
    limit = _get_monitor_limit(user.subscription_type)

    text = (
        f"📊 <b>Мониторинг утечек</b>\n\n"
        f"📧 Email на мониторинге: "
        f"{len(monitored)}/{limit}\n"
        f"🔔 Непрочитанных алертов: {unread_alerts}\n\n"
        f"Мониторинг проверяет ваши email каждые "
        f"6 часов и уведомляет о новых утечках."
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_monitoring_menu_kb(
                has_monitored=len(monitored) > 0
            ),
        )
        await event.answer()
    else:
        await event.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_monitoring_menu_kb(
                has_monitored=len(monitored) > 0
            ),
        )


# ─── Добавление email ────────────────────────────────────

@router.callback_query(F.data == "monitor:add")
async def monitor_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Начало добавления email"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Нужна подписка Premium", show_alert=True
        )
        return

    limit = _get_monitor_limit(user.subscription_type)
    current = await MonitorCRUD.count_user_monitored(
        session, user.id
    )

    if current >= limit:
        await callback.answer(
            f"Достигнут лимит ({limit} email). "
            f"Улучшите тариф.",
            show_alert=True,
        )
        return

    await state.set_state(MonitorStates.waiting_for_email)
    await callback.message.edit_text(
        f"➕ <b>Добавить email на мониторинг</b>\n\n"
        f"Введите email адрес:\n"
        f"Слотов: {current}/{limit}",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )
    await callback.answer()


@router.message(MonitorStates.waiting_for_email)
async def monitor_add_process(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Обработка введённого email для мониторинга"""
    email = message.text.strip().lower()

    if not validate_email(email):
        await message.answer(
            "❌ Некорректный email. Попробуйте снова:",
            reply_markup=get_cancel_kb(),
        )
        return

    user = await UserCRUD.get_by_telegram_id(
        session, message.from_user.id
    )
    if not user:
        await state.clear()
        return

    entry = await MonitorCRUD.add_email(
        session, user.id, email
    )
    await state.clear()

    if entry:
        await message.answer(
            f"✅ <b>Email добавлен на мониторинг!</b>\n\n"
            f"📧 {email}\n\n"
            f"Мы будем проверять его каждые 6 часов "
            f"и уведомим о новых утечках.\n\n"
            f"Первая проверка будет выполнена "
            f"в ближайшем цикле.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⚠️ Этот email уже на мониторинге.",
            parse_mode="HTML",
        )


# ─── Просмотр и добавление через последнюю проверку ──────

@router.callback_query(F.data == "monitor:add_last")
async def monitor_add_last_check(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Добавить последний проверенный email на мониторинг"""
    data = await state.get_data()
    last_query = data.get("last_query")
    last_type = data.get("last_query_type")

    if not last_query or last_type != "email":
        await callback.answer(
            "Нет последней проверки email",
            show_alert=True,
        )
        return

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Нужна подписка Premium",
            show_alert=True,
        )
        return

    limit = _get_monitor_limit(user.subscription_type)
    current = await MonitorCRUD.count_user_monitored(
        session, user.id
    )

    if current >= limit:
        await callback.answer(
            f"Лимит мониторинга ({limit})",
            show_alert=True,
        )
        return

    entry = await MonitorCRUD.add_email(
        session, user.id, last_query
    )

    if entry:
        await callback.answer(
            "✅ Email добавлен на мониторинг!",
            show_alert=True,
        )
    else:
        await callback.answer(
            "Уже на мониторинге", show_alert=True
        )


# ─── Список мониторимых email ─────────────────────────────

@router.callback_query(F.data == "monitor:list")
async def monitor_list(
    callback: CallbackQuery, session: AsyncSession
):
    """Список email на мониторинге"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    monitored = await MonitorCRUD.get_user_monitored(
        session, user.id
    )

    if not monitored:
        await callback.message.edit_text(
            "📋 У вас пока нет email на мониторинге.\n"
            "Нажмите ➕ чтобы добавить.",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📋 <b>Email на мониторинге</b> "
        f"({len(monitored)}):\n\n"
        f"Нажмите на email для подробностей:",
        parse_mode="HTML",
        reply_markup=get_monitored_list_kb(monitored),
    )
    await callback.answer()


# ─── Детали мониторинга ───────────────────────────────────

@router.callback_query(F.data.startswith("monitor:detail:"))
async def monitor_detail(
    callback: CallbackQuery, session: AsyncSession
):
    """Детали мониторимого email"""
    email_id = int(callback.data.split(":")[2])

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    monitored = await MonitorCRUD.get_user_monitored(
        session, user.id
    )
    entry = next((m for m in monitored if m.id == email_id), None)

    if not entry:
        await callback.answer("Не найдено", show_alert=True)
        return

    status = "✅ Активен" if entry.is_active else "❌ Неактивен"
    breach_text = (
        f"🚨 {entry.last_breach_count} утечек"
        if entry.last_breach_count > 0
        else "✅ Утечек не найдено"
    )

    text = (
        f"📧 <b>Мониторинг: {entry.email}</b>\n\n"
        f"├ Статус: {status}\n"
        f"├ Утечки: {breach_text}\n"
        f"├ Последняя проверка: "
        f"{format_date(entry.last_checked)}\n"
        f"└ Добавлен: {format_date(entry.created_at)}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_monitor_detail_kb(email_id),
    )
    await callback.answer()


# ─── Проверить сейчас ─────────────────────────────────────

@router.callback_query(F.data.startswith("monitor:check_now:"))
async def monitor_check_now(
    callback: CallbackQuery, session: AsyncSession
):
    """Принудительная проверка мониторимого email"""
    email_id = int(callback.data.split(":")[2])

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    monitored = await MonitorCRUD.get_user_monitored(
        session, user.id
    )
    entry = next((m for m in monitored if m.id == email_id), None)
    if not entry:
        await callback.answer("Не найдено", show_alert=True)
        return

    await callback.answer("🔍 Проверяю...")

    await callback.message.edit_text(
        f"🔍 Проверяю <code>{entry.email}</code>...",
        parse_mode="HTML",
    )

    result = await leak_checker.check_email(entry.email)

    await MonitorCRUD.update_check_result(
        session, entry.id, result.total_breaches
    )

    text = LeakFormatter.format_result(result)
    if result.breaches:
        for i, breach in enumerate(result.breaches[:3], 1):
            text += LeakFormatter.format_breach(breach, i)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_monitor_detail_kb(email_id),
    )


# ─── Удаление из мониторинга ─────────────────────────────

@router.callback_query(F.data.startswith("monitor:remove:"))
async def monitor_remove(
    callback: CallbackQuery, session: AsyncSession
):
    """Удалить email из мониторинга"""
    email_id = int(callback.data.split(":")[2])

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    removed = await MonitorCRUD.remove_email(
        session, user.id, email_id
    )

    if removed:
        await callback.answer(
            "🗑 Удалено из мониторинга", show_alert=True
        )
        # Обновляем список
        monitored = await MonitorCRUD.get_user_monitored(
            session, user.id
        )
        if monitored:
            await callback.message.edit_text(
                f"📋 <b>Email на мониторинге</b> "
                f"({len(monitored)}):",
                parse_mode="HTML",
                reply_markup=get_monitored_list_kb(monitored),
            )
        else:
            await callback.message.edit_text(
                "📋 Список мониторинга пуст.",
                parse_mode="HTML",
            )
    else:
        await callback.answer("Не найдено", show_alert=True)


# ─── Dark Web ────────────────────────────────────────────

@router.callback_query(F.data == "darkweb:scan")
async def darkweb_scan_all(
    callback: CallbackQuery, session: AsyncSession
):
    """Сканирование dark web для всех мониторимых email"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user or not is_subscription_active(user):
        await callback.answer(
            "Нужна подписка Premium", show_alert=True
        )
        return

    monitored = await MonitorCRUD.get_user_monitored(
        session, user.id
    )
    if not monitored:
        await callback.answer(
            "Добавьте email на мониторинг",
            show_alert=True,
        )
        return

    await callback.answer("🕵️ Запускаю сканирование...")
    await callback.message.edit_text(
        "🕵️ <b>Dark Web сканирование...</b>\n\n"
        f"📧 Сканирую {len(monitored)} email...\n"
        "⏳ Это может занять до 30 секунд.",
        parse_mode="HTML",
    )

    all_findings = []
    for entry in monitored:
        result = await darkweb_service.scan(
            entry.email, "email"
        )
        if result.has_findings:
            all_findings.extend(result.findings)

    if all_findings:
        text = DarkWebFormatter.format_scan_result(
            type(
                "Result",
                (),
                {
                    "query": "все email",
                    "has_findings": True,
                    "findings": all_findings,
                    "scanned_sources": 8,
                    "max_severity": max(
                        all_findings,
                        key=lambda f: {
                            "critical": 0,
                            "high": 1,
                            "medium": 2,
                            "low": 3,
                        }.get(f.severity, 99),
                    ).severity,
                    "error": None,
                },
            )()
        )
    else:
        text = (
            "🕵️ <b>Dark Web сканирование завершено</b>\n\n"
            "✅ Данные не обнаружены в dark web!\n\n"
            f"Просканировано {len(monitored)} email "
            f"по 8 источникам."
        )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_darkweb_alerts_kb(
            has_unread=len(all_findings) > 0
        ),
    )


@router.callback_query(F.data.startswith("darkweb:scan_email:"))
async def darkweb_scan_single(
    callback: CallbackQuery, session: AsyncSession
):
    """Dark web скан одного email"""
    email_id = int(callback.data.split(":")[2])

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    monitored = await MonitorCRUD.get_user_monitored(
        session, user.id
    )
    entry = next((m for m in monitored if m.id == email_id), None)
    if not entry:
        await callback.answer("Не найдено", show_alert=True)
        return

    await callback.answer("🕵️ Сканирую...")
    await callback.message.edit_text(
        f"🕵️ Сканирую dark web: "
        f"<code>{entry.email}</code>...",
        parse_mode="HTML",
    )

    result = await darkweb_service.scan(entry.email, "email")
    text = DarkWebFormatter.format_scan_result(result)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_monitor_detail_kb(email_id),
    )


# ─── Алерты Dark Web ─────────────────────────────────────

@router.callback_query(F.data == "darkweb:alerts")
async def darkweb_alerts(
    callback: CallbackQuery, session: AsyncSession
):
    """Показать алерты dark web"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    alerts = await DarkWebCRUD.get_user_alerts(
        session, user.id, limit=10
    )
    unread = await DarkWebCRUD.count_unread(session, user.id)

    if not alerts:
        text = (
            "🔔 <b>Алерты Dark Web</b>\n\n"
            "Нет алертов. Это хорошо!\n\n"
            "Мы уведомим вас, если ваши данные "
            "появятся в dark web."
        )
    else:
        severity_emoji = {
            "critical": "⛔",
            "high": "🔴",
            "medium": "🟠",
            "low": "🟡",
        }

        lines = [
            f"🔔 <b>Алерты Dark Web</b> "
            f"(непрочитанных: {unread})\n",
        ]
        for alert in alerts:
            emoji = severity_emoji.get(alert.severity, "🟠")
            read = "" if alert.is_read else " 🆕"
            lines.append(
                f"{emoji} {alert.source} — "
                f"{alert.matched_data}{read}\n"
                f"   📅 {format_date(alert.created_at)}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_darkweb_alerts_kb(
            has_unread=unread > 0
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "darkweb:read_all")
async def darkweb_read_all(
    callback: CallbackQuery, session: AsyncSession
):
    """Пометить все алерты прочитанными"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if user:
        await DarkWebCRUD.mark_read(session, user.id)
    await callback.answer(
        "✅ Все алерты прочитаны", show_alert=True
    )