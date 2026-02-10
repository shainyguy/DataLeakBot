from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_monitoring_menu_kb(
    has_monitored: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить email",
            callback_data="monitor:add",
        )
    )

    if has_monitored:
        builder.row(
            InlineKeyboardButton(
                text="📋 Мои мониторинги",
                callback_data="monitor:list",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🕵️ Dark Web сканирование",
                callback_data="darkweb:scan",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔔 Алерты Dark Web",
                callback_data="darkweb:alerts",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="👨‍👩‍👧 Семейный мониторинг",
            callback_data="family:menu",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Меню", callback_data="back:menu"
        )
    )
    return builder.as_markup()


def get_monitored_list_kb(
    emails: list,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for email_entry in emails:
        status = "✅" if email_entry.is_active else "❌"
        breach_info = ""
        if email_entry.last_breach_count > 0:
            breach_info = f" ⚠️{email_entry.last_breach_count}"

        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{status} {email_entry.email[:25]}"
                    f"{breach_info}"
                ),
                callback_data=f"monitor:detail:{email_entry.id}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить",
            callback_data="monitor:add",
        ),
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="monitor:menu",
        ),
    )
    return builder.as_markup()


def get_monitor_detail_kb(
    email_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔍 Проверить сейчас",
            callback_data=f"monitor:check_now:{email_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🕵️ Dark Web скан",
            callback_data=f"darkweb:scan_email:{email_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить из мониторинга",
            callback_data=f"monitor:remove:{email_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="monitor:list",
        )
    )
    return builder.as_markup()


def get_family_menu_kb(
    has_members: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить члена семьи",
            callback_data="family:add",
        )
    )
    if has_members:
        builder.row(
            InlineKeyboardButton(
                text="👨‍👩‍👧 Список семьи",
                callback_data="family:list",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔍 Проверить всю семью",
                callback_data="family:check_all",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="monitor:menu",
        )
    )
    return builder.as_markup()


def get_darkweb_alerts_kb(
    has_unread: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_unread:
        builder.row(
            InlineKeyboardButton(
                text="✅ Пометить все прочитанными",
                callback_data="darkweb:read_all",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Запустить сканирование",
            callback_data="darkweb:scan",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="monitor:menu",
        )
    )
    return builder.as_markup()