import re
import hashlib
from datetime import datetime, timezone
from database.models import SubscriptionType


def validate_email(email: str) -> bool:
    """Валидация email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def validate_phone(phone: str) -> bool:
    """Валидация российского телефона"""
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    pattern = r'^[78]?\d{10}$'
    return bool(re.match(pattern, cleaned))


def normalize_phone(phone: str) -> str:
    """Нормализует номер телефона"""
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    if cleaned.startswith('8') and len(cleaned) == 11:
        cleaned = '7' + cleaned[1:]
    if not cleaned.startswith('7'):
        cleaned = '7' + cleaned
    return '+' + cleaned


def hash_value(value: str) -> str:
    """SHA-256 хеш значения"""
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()


def format_subscription_name(sub_type: SubscriptionType) -> str:
    names = {
        SubscriptionType.FREE: "🆓 Free",
        SubscriptionType.PREMIUM: "⭐ Premium",
        SubscriptionType.BUSINESS: "🏢 Business",
    }
    return names.get(sub_type, "Unknown")


def format_date(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def is_subscription_active(user) -> bool:
    """Проверяет, активна ли подписка"""
    if user.subscription_type == SubscriptionType.FREE:
        return False
    if not user.subscription_expires:
        return False
    return user.subscription_expires > datetime.now(timezone.utc)


def days_until_expiry(user) -> int:
    """Дней до истечения подписки"""
    if not user.subscription_expires:
        return 0
    delta = user.subscription_expires - datetime.now(timezone.utc)
    return max(0, delta.days)


# ─── Текстовые шаблоны ──────────────────────────────────

WELCOME_TEXT = """
🛡 <b>DataLeakBot</b> — Проверка утечек данных

Я помогу узнать, попали ли ваши данные в утечки:

🔍 <b>Что я умею:</b>
├ Проверка email на утечки
├ Проверка телефона
├ Проверка стойкости пароля
├ Мониторинг новых утечек
├ Рекомендации по безопасности
└ Dark Web мониторинг

📊 <b>Ваш тариф:</b> {plan}
📅 <b>Регистрация:</b> {reg_date}

Выберите действие ниже 👇
"""

PROFILE_TEXT = """
👤 <b>Ваш профиль</b>

├ 🆔 ID: <code>{telegram_id}</code>
├ 👤 Имя: {full_name}
├ 📊 Тариф: {plan}
├ 📅 Действует до: {expires}
├ 🔍 Проверок сегодня: {checks_today}
├ 📈 Всего проверок: {total_checks}
├ 🔗 Реферальный код: <code>{referral_code}</code>
└ 💰 Реферальный баланс: {referral_earnings}₽

{subscription_info}
"""

SUBSCRIPTION_TEXT = """
💎 <b>Тарифные планы DataLeakBot</b>

🆓 <b>Free</b> — Бесплатно
├ 1 проверка в день
├ Проверка email
└ Базовые рекомендации

⭐ <b>Premium</b> — 790₽/мес
├ Безлимитные проверки
├ Мониторинг email и телефонов
├ Dark Web мониторинг
├ Проверка паролей
├ ИИ-рекомендации (GigaChat)
├ До 5 email на мониторинге
└ Семейный доступ (до 3 человек)

🏢 <b>Business</b> — 1 790₽/мес
├ Всё из Premium
├ Мониторинг корпоративного домена
├ До 50 email на мониторинге
├ API доступ
├ Приоритетная поддержка
└ Отчёты для руководства

Выберите тариф для оформления 👇
"""

PAYMENT_SUCCESS_TEXT = """
✅ <b>Оплата прошла успешно!</b>

├ 📊 Тариф: {plan}
├ 💰 Сумма: {amount}₽
├ 📅 Активен до: {expires}

Спасибо за доверие! 🛡
Теперь вам доступны все возможности тарифа.

Нажмите /menu для начала работы.
"""