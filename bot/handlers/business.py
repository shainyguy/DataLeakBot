"""
Обработчики бизнес-функций.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD, BusinessCRUD
from database.models import SubscriptionType
from bot.keyboards.business_kb import (
    get_business_menu_kb,
    get_domain_detail_kb,
)
from bot.keyboards.main_kb import get_cancel_kb
from bot.services.business_service import BusinessService
from bot.utils.helpers import is_subscription_active, format_date

router = Router()
business_service = BusinessService()


class BusinessStates(StatesGroup):
    waiting_for_domain = State()
    waiting_for_company = State()


# ─── Меню бизнеса ────────────────────────────────────────

@router.message(Command("business"))
@router.callback_query(F.data == "biz:menu")
async def business_menu(
    event: Message | CallbackQuery,
    session: AsyncSession,
):
    """Бизнес-меню"""
    tg_id = event.from_user.id
    user = await UserCRUD.get_by_telegram_id(session, tg_id)

    if not user:
        text = "Нажмите /start"
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return

    if (
        user.subscription_type != SubscriptionType.BUSINESS
        or not is_subscription_active(user)
    ):
        text = (
            "🏢 <b>Business-тариф</b>\n\n"
            "Корпоративный мониторинг доступен "
            "только для тарифа Business (1790₽/мес).\n\n"
            "Возможности:\n"
            "├ Мониторинг корпоративного домена\n"
            "├ До 50 email на мониторинге\n"
            "├ Отчёты для руководства\n"
            "├ Приоритетная поддержка\n"
            "└ Всё из Premium\n\n"
            "/subscribe — оформить подписку"
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(
                text, parse_mode="HTML"
            )
            await event.answer()
        else:
            await event.answer(text, parse_mode="HTML")
        return

    domains = await BusinessCRUD.get_domains(session, user.id)

    text = (
        f"🏢 <b>Корпоративный мониторинг</b>\n\n"
        f"📊 Доменов: {len(domains)}\n\n"
        f"Мониторинг корпоративных email-адресов "
        f"на утечки данных."
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_business_menu_kb(
                has_domains=len(domains) > 0
            ),
        )
        await event.answer()
    else:
        await event.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_business_menu_kb(
                has_domains=len(domains) > 0
            ),
        )


# ─── Добавление домена ───────────────────────────────────

@router.callback_query(F.data == "biz:add_domain")
async def biz_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if (
        not user
        or user.subscription_type != SubscriptionType.BUSINESS
    ):
        await callback.answer(
            "Нужен Business тариф", show_alert=True
        )
        return

    await state.set_state(BusinessStates.waiting_for_domain)
    await callback.message.edit_text(
        "🏢 <b>Добавление домена</b>\n\n"
        "Введите корпоративный домен:\n\n"
        "<i>Пример: company.ru</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )
    await callback.answer()


@router.message(BusinessStates.waiting_for_domain)
async def biz_add_domain(
    message: Message, state: FSMContext
):
    domain = message.text.strip().lower()

    # Простая валидация домена
    if "." not in domain or len(domain) < 4:
        await message.answer(
            "❌ Некорректный домен. Пример: company.ru",
            reply_markup=get_cancel_kb(),
        )
        return

    # Убираем http/www
    domain = domain.replace("http://", "").replace("https://", "")
    domain = domain.replace("www.", "")
    domain = domain.split("/")[0]

    await state.update_data(biz_domain=domain)
    await state.set_state(BusinessStates.waiting_for_company)
    await message.answer(
        f"🌐 Домен: <b>{domain}</b>\n\n"
        "Введите название компании "
        "(или «-» чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=get_cancel_kb(),
    )


@router.message(BusinessStates.waiting_for_company)
async def biz_add_company(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    domain = data.get("biz_domain", "")
    company = message.text.strip()
    if company == "-":
        company = ""

    user = await UserCRUD.get_by_telegram_id(
        session, message.from_user.id
    )
    if not user:
        await state.clear()
        return

    entry = await BusinessCRUD.add_domain(
        session, user.id, domain, company
    )
    await state.clear()

    if entry:
        await message.answer(
            f"✅ <b>Домен добавлен!</b>\n\n"
            f"🌐 {domain}\n"
            f"🏢 {company or 'Без названия'}\n\n"
            f"Запустите сканирование через меню /business",
            parse_mode="HTML",
        )
    else:
        await message.answer("⚠️ Домен уже добавлен.")


# ─── Список доменов ──────────────────────────────────────

@router.callback_query(F.data == "biz:list_domains")
async def biz_list_domains(
    callback: CallbackQuery, session: AsyncSession
):
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    domains = await BusinessCRUD.get_domains(session, user.id)

    if not domains:
        await callback.answer(
            "Нет доменов", show_alert=True
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    for d in domains:
        breach_info = ""
        if d.total_breaches_found > 0:
            breach_info = f" ⚠️{d.total_breaches_found}"
        builder.row(
            InlineKeyboardButton(
                text=f"🌐 {d.domain}{breach_info}",
                callback_data=f"biz:domain_detail:{d.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="biz:menu",
        )
    )

    await callback.message.edit_text(
        "🏢 <b>Ваши домены:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


# ─── Детали домена ────────────────────────────────────────

@router.callback_query(F.data.startswith("biz:domain_detail:"))
async def biz_domain_detail(
    callback: CallbackQuery, session: AsyncSession
):
    domain_id = int(callback.data.split(":")[2])
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    domains = await BusinessCRUD.get_domains(session, user.id)
    domain = next((d for d in domains if d.id == domain_id), None)
    if not domain:
        await callback.answer("Не найдено", show_alert=True)
        return

    text = (
        f"🌐 <b>Домен: {domain.domain}</b>\n"
        f"🏢 Компания: {domain.company_name or '—'}\n\n"
        f"📊 Утечек: {domain.total_breaches_found}\n"
        f"📧 Email в утечках: {domain.total_emails_found}\n"
        f"📅 Последнее сканирование: "
        f"{format_date(domain.last_scan)}\n"
        f"📅 Добавлен: {format_date(domain.created_at)}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_domain_detail_kb(domain_id),
    )
    await callback.answer()


# ─── Сканирование домена ─────────────────────────────────

@router.callback_query(F.data == "biz:scan")
async def biz_scan_select(
    callback: CallbackQuery, session: AsyncSession
):
    """Выбор домена для сканирования"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    domains = await BusinessCRUD.get_domains(session, user.id)
    if not domains:
        await callback.answer(
            "Сначала добавьте домен", show_alert=True
        )
        return

    # Если один домен — сканируем сразу
    if len(domains) == 1:
        await _scan_domain(callback, session, domains[0])
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    for d in domains:
        builder.row(
            InlineKeyboardButton(
                text=f"🔍 {d.domain}",
                callback_data=f"biz:scan_domain:{d.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="biz:menu",
        )
    )

    await callback.message.edit_text(
        "🔍 Выберите домен для сканирования:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("biz:scan_domain:"))
async def biz_scan_domain(
    callback: CallbackQuery, session: AsyncSession
):
    domain_id = int(callback.data.split(":")[2])
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    domains = await BusinessCRUD.get_domains(session, user.id)
    domain = next((d for d in domains if d.id == domain_id), None)
    if not domain:
        await callback.answer("Не найдено", show_alert=True)
        return

    await _scan_domain(callback, session, domain)


async def _scan_domain(callback, session, domain):
    """Выполнить сканирование домена"""
    await callback.answer("🔍 Сканирую...")
    await callback.message.edit_text(
        f"🔍 Сканирую домен <b>{domain.domain}</b>...\n"
        f"⏳ Это может занять до 30 секунд.",
        parse_mode="HTML",
    )

    result = await business_service.scan_domain(domain.domain)

    # Сохраняем результат
    await BusinessCRUD.update_scan_results(
        session,
        domain.id,
        result.total_emails_exposed,
        result.total_breaches,
        {
            "breaches": [
                {
                    "name": b.get("Name"),
                    "title": b.get("Title"),
                    "date": b.get("BreachDate"),
                    "count": b.get("PwnCount"),
                }
                for b in result.breaches[:20]
            ],
            "data_types": result.data_types_exposed,
        },
    )

    text = BusinessService.format_domain_report(result)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_domain_detail_kb(domain.id),
    )


# ─── Отчёт для руководства ───────────────────────────────

@router.callback_query(F.data == "biz:report")
@router.callback_query(F.data.startswith("biz:report_domain:"))
async def biz_executive_report(
    callback: CallbackQuery, session: AsyncSession
):
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    domains = await BusinessCRUD.get_domains(session, user.id)
    if not domains:
        await callback.answer(
            "Нет доменов", show_alert=True
        )
        return

    # Определяем какой домен
    if ":" in callback.data and callback.data.count(":") >= 2:
        parts = callback.data.split(":")
        if len(parts) >= 3 and parts[2].isdigit():
            domain_id = int(parts[2])
            domain = next(
                (d for d in domains if d.id == domain_id), None
            )
        else:
            domain = domains[0]
    else:
        domain = domains[0]

    if not domain:
        await callback.answer("Не найдено", show_alert=True)
        return

    await callback.answer("📊 Формирую отчёт...")

    # Если нет результатов — сканируем
    if not domain.last_scan:
        await callback.message.edit_text(
            "📊 Формирую отчёт...\n🔍 Нужно сканирование...",
            parse_mode="HTML",
        )
        result = await business_service.scan_domain(
            domain.domain
        )
    else:
        # Используем сохранённые результаты
        result = type("R", (), {
            "domain": domain.domain,
            "total_breaches": domain.total_breaches_found,
            "total_emails_exposed": domain.total_emails_found,
            "data_types_exposed": (
                domain.scan_results.get("data_types", [])
                if domain.scan_results
                else []
            ),
            "breaches": (
                domain.scan_results.get("breaches", [])
                if domain.scan_results
                else []
            ),
            "scanned_at": domain.last_scan,
            "error": None,
        })()

    text = BusinessService.format_executive_report(
        result, domain.company_name
    )

    await callback.message.edit_text(
        text, parse_mode="HTML"
    )


# ─── Удаление домена ─────────────────────────────────────

@router.callback_query(F.data.startswith("biz:remove_domain:"))
async def biz_remove_domain(
    callback: CallbackQuery, session: AsyncSession
):
    domain_id = int(callback.data.split(":")[2])
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    removed = await BusinessCRUD.remove_domain(
        session, user.id, domain_id
    )

    if removed:
        await callback.answer("🗑 Домен удалён", show_alert=True)
        await callback.message.edit_text(
            "🗑 Домен удалён из мониторинга.",
            parse_mode="HTML",
        )
    else:
        await callback.answer("Не найдено", show_alert=True)


# ─── Отмена FSM ──────────────────────────────────────────

@router.callback_query(
    F.data == "cancel",
    BusinessStates.waiting_for_domain,
)
@router.callback_query(
    F.data == "cancel",
    BusinessStates.waiting_for_company,
)
async def cancel_biz(
    callback: CallbackQuery, state: FSMContext
):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()