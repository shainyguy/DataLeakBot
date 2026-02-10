from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="admin:stats",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💰 Доходы",
            callback_data="admin:revenue",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 Пользователи",
            callback_data="admin:users",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📢 Рассылка",
            callback_data="admin:broadcast",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🎁 Выдать подписку",
            callback_data="admin:grant",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔍 Найти пользователя",
            callback_data="admin:find_user",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Меню",
            callback_data="back:menu",
        )
    )
    return builder.as_markup()


def get_admin_users_kb(
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Фильтры
    builder.row(
        InlineKeyboardButton(
            text="Все",
            callback_data="admin:users:all:0",
        ),
        InlineKeyboardButton(
            text="⭐ Premium",
            callback_data="admin:users:premium:0",
        ),
        InlineKeyboardButton(
            text="🏢 Business",
            callback_data="admin:users:business:0",
        ),
    )

    # Навигация
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"admin:users:all:{page - 1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="noop",
        )
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"admin:users:all:{page + 1}",
            )
        )
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(
            text="🔙 Админка",
            callback_data="admin:menu",
        )
    )
    return builder.as_markup()


def get_admin_user_actions_kb(
    telegram_id: int,
    is_blocked: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_blocked:
        builder.row(
            InlineKeyboardButton(
                text="✅ Разблокировать",
                callback_data=f"admin:unblock:{telegram_id}",
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🚫 Заблокировать",
                callback_data=f"admin:block:{telegram_id}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⭐ Выдать Premium (30д)",
            callback_data=f"admin:give_prem:{telegram_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏢 Выдать Business (30д)",
            callback_data=f"admin:give_biz:{telegram_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="admin:users",
        )
    )
    return builder.as_markup()