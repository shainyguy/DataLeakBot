from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_check_result_kb(
    has_breaches: bool = False,
    is_premium: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура после результата проверки"""
    builder = InlineKeyboardBuilder()

    if has_breaches:
        if is_premium:
            builder.row(
                InlineKeyboardButton(
                    text="🤖 ИИ-рекомендации",
                    callback_data="ai:recommendations",
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="🤖 ИИ-рекомендации (Premium)",
                    callback_data="subscription:show",
                )
            )

        builder.row(
            InlineKeyboardButton(
                text="📊 Добавить в мониторинг",
                callback_data="monitor:add_last",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🔍 Проверить ещё",
            callback_data="check:new",
        ),
        InlineKeyboardButton(
            text="📋 История",
            callback_data="history:show",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Меню",
            callback_data="back:menu",
        )
    )
    return builder.as_markup()


def get_password_result_kb(
    is_premium: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура после проверки пароля"""
    builder = InlineKeyboardBuilder()

    if is_premium:
        builder.row(
            InlineKeyboardButton(
                text="🤖 ИИ-совет по паролю",
                callback_data="ai:password_advice",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🔑 Проверить другой пароль",
            callback_data="password:new",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔍 Проверить email/телефон",
            callback_data="check:new",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Меню",
            callback_data="back:menu",
        )
    )
    return builder.as_markup()


def get_history_kb(
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """Клавиатура навигации по истории"""
    builder = InlineKeyboardBuilder()

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"history:page:{page - 1}",
            )
        )
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="noop",
        )
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"history:page:{page + 1}",
            )
        )

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(
            text="🔍 Новая проверка",
            callback_data="check:new",
        ),
        InlineKeyboardButton(
            text="🔙 Меню",
            callback_data="back:menu",
        ),
    )
    return builder.as_markup()


def get_breach_navigation_kb(
    current: int,
    total: int,
    query_type: str = "email",
) -> InlineKeyboardMarkup:
    """Навигация по списку утечек"""
    builder = InlineKeyboardBuilder()

    nav_buttons = []
    if current > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️ Пред.",
                callback_data=f"breach:prev:{current}",
            )
        )
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{current + 1}/{total}",
            callback_data="noop",
        )
    )
    if current < total - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="След. ▶️",
                callback_data=f"breach:next:{current}",
            )
        )

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(
            text="📊 Все утечки списком",
            callback_data="breach:all",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 К результатам",
            callback_data="breach:back_to_result",
        )
    )
    return builder.as_markup()