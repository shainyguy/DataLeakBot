from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_business_menu_kb(
    has_domains: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить домен",
            callback_data="biz:add_domain",
        )
    )

    if has_domains:
        builder.row(
            InlineKeyboardButton(
                text="🏢 Мои домены",
                callback_data="biz:list_domains",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔍 Сканировать домен",
                callback_data="biz:scan",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="📊 Отчёт для руководства",
                callback_data="biz:report",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🔙 Меню",
            callback_data="back:menu",
        )
    )
    return builder.as_markup()


def get_domain_detail_kb(domain_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔍 Сканировать сейчас",
            callback_data=f"biz:scan_domain:{domain_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Скачать отчёт",
            callback_data=f"biz:report_domain:{domain_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=f"biz:remove_domain:{domain_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="biz:list_domains",
        )
    )
    return builder.as_markup()