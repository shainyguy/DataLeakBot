"""
Обработчики истории проверок.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD, CheckHistoryCRUD
from bot.keyboards.check_kb import get_history_kb
from bot.utils.helpers import format_date

router = Router()

ITEMS_PER_PAGE = 5


@router.message(F.text == "📋 История")
@router.message(Command("history"))
@router.callback_query(F.data == "history:show")
async def show_history(
    event: Message | CallbackQuery,
    session: AsyncSession,
):
    """Показать историю проверок"""
    tg_id = event.from_user.id
    user = await UserCRUD.get_by_telegram_id(session, tg_id)

    if not user:
        text = "Нажмите /start для начала работы."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return

    history = await CheckHistoryCRUD.get_user_history(
        session, user.id, limit=50
    )

    if not history:
        text = (
            "📋 <b>История проверок</b>\n\n"
            "У вас пока нет проверок.\n"
            "Нажмите 🔍 <b>Проверить данные</b> для начала."
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(
                text, parse_mode="HTML"
            )
            await event.answer()
        else:
            await event.answer(text, parse_mode="HTML")
        return

    page = 0
    text = _format_history_page(history, page)
    total_pages = max(1, (len(history) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_history_kb(page, total_pages),
        )
        await event.answer()
    else:
        await event.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_history_kb(page, total_pages),
        )


@router.callback_query(F.data.startswith("history:page:"))
async def history_page(
    callback: CallbackQuery, session: AsyncSession
):
    """Переключение страниц истории"""
    page = int(callback.data.split(":")[2])

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    history = await CheckHistoryCRUD.get_user_history(
        session, user.id, limit=50
    )

    total_pages = max(1, (len(history) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    text = _format_history_page(history, page)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_history_kb(page, total_pages),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Пустой обработчик для некликабельных кнопок"""
    await callback.answer()


def _format_history_page(history: list, page: int) -> str:
    """Форматирует страницу истории"""
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = history[start:end]

    type_emoji = {
        "email": "📧",
        "phone": "📱",
        "password": "🔑",
        "username": "👤",
    }

    lines = [
        f"📋 <b>История проверок</b> "
        f"({len(history)} всего)\n",
    ]

    for i, item in enumerate(page_items, start + 1):
        check_type = item.check_type.value if hasattr(
            item.check_type, "value"
        ) else str(item.check_type)
        emoji = type_emoji.get(check_type, "🔍")

        breach_text = ""
        if item.breaches_found > 0:
            breach_text = f" — 🚨 {item.breaches_found} утечек"
        else:
            breach_text = " — ✅ чисто"

        lines.append(
            f"{i}. {emoji} <code>{item.query_value}</code>"
            f"{breach_text}\n"
            f"   📅 {format_date(item.created_at)}"
        )

    return "\n".join(lines)