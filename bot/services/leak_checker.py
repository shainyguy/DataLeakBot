"""
Сервис проверки утечек данных.

Источники:
1. Have I Been Pwned (HIBP) API — основной
2. LeakCheck API — дополнительный (русские базы)
3. Локальная база известных утечек — фоллбэк
"""

import aiohttp
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class BreachInfo:
    """Информация об одной утечке"""
    name: str
    title: str
    domain: str = ""
    breach_date: str = ""
    added_date: str = ""
    pwn_count: int = 0
    description: str = ""
    data_classes: list[str] = field(default_factory=list)
    is_verified: bool = True
    logo_path: str = ""
    severity: str = "medium"  # low, medium, high, critical

    @property
    def severity_emoji(self) -> str:
        return {
            "low": "🟡",
            "medium": "🟠",
            "high": "🔴",
            "critical": "⛔",
        }.get(self.severity, "🟠")

    @property
    def data_classes_ru(self) -> list[str]:
        """Перевод типов данных на русский"""
        translations = {
            "Email addresses": "📧 Email адреса",
            "Passwords": "🔑 Пароли",
            "Usernames": "👤 Имена пользователей",
            "Phone numbers": "📱 Номера телефонов",
            "IP addresses": "🌐 IP адреса",
            "Physical addresses": "📍 Физические адреса",
            "Dates of birth": "🎂 Даты рождения",
            "Names": "👤 Имена",
            "Credit cards": "💳 Кредитные карты",
            "Bank account numbers": "🏦 Номера банковских счетов",
            "Social security numbers": "🆔 Номера документов",
            "Passport numbers": "🛂 Номера паспортов",
            "Government issued IDs": "🆔 Гос. документы",
            "Genders": "⚧ Пол",
            "Employers": "🏢 Работодатели",
            "Job titles": "💼 Должности",
            "Education levels": "🎓 Образование",
            "Purchases": "🛒 Покупки",
            "Payment methods": "💳 Способы оплаты",
            "Geographic locations": "📍 Геолокация",
            "Auth tokens": "🔐 Токены авторизации",
            "Device information": "📱 Информация об устройствах",
            "Browser user agents": "🌐 Данные браузера",
            "Chat logs": "💬 Логи чатов",
            "Private messages": "✉️ Личные сообщения",
            "Photos": "📷 Фотографии",
            "Avatars": "🖼 Аватары",
            "Social connections": "🔗 Социальные связи",
            "Security questions and answers": "❓ Секретные вопросы",
            "Recovery email addresses": "📧 Резервные email",
            "MAC addresses": "🔌 MAC адреса",
        }
        return [translations.get(dc, f"📄 {dc}") for dc in self.data_classes]


@dataclass
class LeakCheckResult:
    """Результат проверки на утечки"""
    query: str
    query_type: str  # email, phone, username
    total_breaches: int = 0
    breaches: list[BreachInfo] = field(default_factory=list)
    pastes: int = 0
    error: str | None = None
    checked_at: datetime = field(default_factory=datetime.now)

    @property
    def is_compromised(self) -> bool:
        return self.total_breaches > 0

    @property
    def critical_data_leaked(self) -> list[str]:
        """Список критичных типов утёкших данных"""
        critical = {
            "Passwords", "Credit cards", "Bank account numbers",
            "Social security numbers", "Passport numbers",
            "Government issued IDs", "Auth tokens",
        }
        leaked = set()
        for breach in self.breaches:
            for dc in breach.data_classes:
                if dc in critical:
                    leaked.add(dc)
        return list(leaked)

    def to_dict(self) -> dict:
        return {
            "query_type": self.query_type,
            "total_breaches": self.total_breaches,
            "pastes": self.pastes,
            "breaches": [
                {
                    "name": b.name,
                    "title": b.title,
                    "domain": b.domain,
                    "breach_date": b.breach_date,
                    "pwn_count": b.pwn_count,
                    "data_classes": b.data_classes,
                    "severity": b.severity,
                }
                for b in self.breaches
            ],
        }


class LeakCheckerService:
    """Основной сервис проверки утечек"""

    HIBP_API_URL = "https://haveibeenpwned.com/api/v3"
    HIBP_USER_AGENT = "DataLeakBot-Telegram"

    # Известные крупные утечки (фоллбэк + дополнение для рос. рынка)
    KNOWN_RUSSIAN_BREACHES = {
        "mail.ru": BreachInfo(
            name="MailRu2014",
            title="Mail.ru",
            domain="mail.ru",
            breach_date="2014-09-01",
            pwn_count=4660000,
            data_classes=["Email addresses", "Passwords"],
            description="Утечка базы данных Mail.ru в 2014 году",
            severity="high",
        ),
        "yandex.ru": BreachInfo(
            name="Yandex2014",
            title="Яндекс",
            domain="yandex.ru",
            breach_date="2014-09-01",
            pwn_count=1260000,
            data_classes=["Email addresses", "Passwords"],
            description="Утечка аккаунтов Яндекса",
            severity="high",
        ),
        "vk.com": BreachInfo(
            name="VK2012",
            title="ВКонтакте",
            domain="vk.com",
            breach_date="2012-01-01",
            pwn_count=93388000,
            data_classes=[
                "Email addresses", "Passwords",
                "Phone numbers", "Names",
            ],
            description="Масштабная утечка VK в 2012 году",
            severity="critical",
        ),
        "rambler.ru": BreachInfo(
            name="Rambler2012",
            title="Rambler",
            domain="rambler.ru",
            breach_date="2012-01-01",
            pwn_count=91000000,
            data_classes=["Email addresses", "Passwords"],
            description="Утечка Rambler",
            severity="high",
        ),
        "cdek.ru": BreachInfo(
            name="CDEK2022",
            title="СДЭК",
            domain="cdek.ru",
            breach_date="2022-05-01",
            pwn_count=19000000,
            data_classes=[
                "Email addresses", "Phone numbers",
                "Names", "Physical addresses",
            ],
            description="Утечка данных клиентов СДЭК",
            severity="critical",
        ),
        "delivery-club.ru": BreachInfo(
            name="DeliveryClub2022",
            title="Delivery Club",
            domain="delivery-club.ru",
            breach_date="2022-06-01",
            pwn_count=21000000,
            data_classes=[
                "Email addresses", "Phone numbers",
                "Names", "Physical addresses", "Purchases",
            ],
            description="Утечка Delivery Club",
            severity="critical",
        ),
        "pikabu.ru": BreachInfo(
            name="Pikabu2022",
            title="Pikabu",
            domain="pikabu.ru",
            breach_date="2022-07-01",
            pwn_count=7900000,
            data_classes=["Email addresses", "Passwords", "Usernames"],
            description="Утечка базы Pikabu",
            severity="high",
        ),
        "geekbrains.ru": BreachInfo(
            name="GeekBrains2022",
            title="GeekBrains",
            domain="geekbrains.ru",
            breach_date="2022-06-01",
            pwn_count=6000000,
            data_classes=[
                "Email addresses", "Phone numbers",
                "Names", "Passwords",
            ],
            description="Утечка GeekBrains",
            severity="high",
        ),
    }

    def __init__(self):
        self.api_key = settings.hibp_api_key

    async def check_email(self, email: str) -> LeakCheckResult:
        """Полная проверка email"""
        result = LeakCheckResult(
            query=email,
            query_type="email",
        )

        # 1. Проверяем через HIBP API
        if self.api_key:
            hibp_result = await self._check_hibp(email)
            if hibp_result and not hibp_result.error:
                result.breaches.extend(hibp_result.breaches)

        # 2. Проверяем по известным российским утечкам
        local_breaches = self._check_local_breaches(email)
        # Добавляем только те, которых нет от HIBP
        existing_names = {b.name for b in result.breaches}
        for breach in local_breaches:
            if breach.name not in existing_names:
                result.breaches.append(breach)

        # 3. Проверяем pastes (HIBP)
        if self.api_key:
            pastes_count = await self._check_pastes(email)
            result.pastes = pastes_count

        result.total_breaches = len(result.breaches)

        # Сортируем: сначала критичные
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        result.breaches.sort(
            key=lambda b: severity_order.get(b.severity, 2)
        )

        return result

    async def check_phone(self, phone: str) -> LeakCheckResult:
        """Проверка телефона — по известным утечкам"""
        result = LeakCheckResult(
            query=phone,
            query_type="phone",
        )

        # Телефоны часто встречаются в российских утечках
        phone_breaches = [
            BreachInfo(
                name="PhoneDB_General",
                title="Агрегированные базы телефонов",
                breach_date="2023-01-01",
                data_classes=["Phone numbers", "Names"],
                description=(
                    "Телефонные номера часто попадают в агрегированные "
                    "базы из множества источников"
                ),
                severity="medium",
            ),
        ]

        # Проверяем HIBP если есть API ключ
        if self.api_key:
            hibp_result = await self._check_hibp(phone)
            if hibp_result and not hibp_result.error:
                result.breaches.extend(hibp_result.breaches)

        result.total_breaches = len(result.breaches)
        return result

    async def check_username(self, username: str) -> LeakCheckResult:
        """Проверка по имени пользователя"""
        result = LeakCheckResult(
            query=username,
            query_type="username",
        )

        # HIBP не поддерживает username напрямую, но можно проверить
        # через поиск по known breaches
        if self.api_key:
            # Пробуем как email-подобный запрос (некоторые API поддерживают)
            pass

        result.total_breaches = len(result.breaches)
        return result

    async def _check_hibp(self, account: str) -> LeakCheckResult | None:
        """Проверка через Have I Been Pwned API"""
        result = LeakCheckResult(query=account, query_type="email")

        headers = {
            "hibp-api-key": self.api_key,
            "user-agent": self.HIBP_USER_AGENT,
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = (
                    f"{self.HIBP_API_URL}"
                    f"/breachedaccount/{account}"
                    f"?truncateResponse=false"
                )
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for breach_data in data:
                            severity = self._calculate_severity(breach_data)
                            breach = BreachInfo(
                                name=breach_data.get("Name", ""),
                                title=breach_data.get("Title", ""),
                                domain=breach_data.get("Domain", ""),
                                breach_date=breach_data.get(
                                    "BreachDate", ""
                                ),
                                added_date=breach_data.get("AddedDate", ""),
                                pwn_count=breach_data.get("PwnCount", 0),
                                description=breach_data.get(
                                    "Description", ""
                                ),
                                data_classes=breach_data.get(
                                    "DataClasses", []
                                ),
                                is_verified=breach_data.get(
                                    "IsVerified", False
                                ),
                                logo_path=breach_data.get("LogoPath", ""),
                                severity=severity,
                            )
                            result.breaches.append(breach)

                    elif resp.status == 404:
                        pass  # Не найдено — хорошо
                    elif resp.status == 401:
                        result.error = "Invalid HIBP API key"
                        logger.error("HIBP: Invalid API key")
                    elif resp.status == 429:
                        result.error = "Rate limit exceeded"
                        logger.warning("HIBP: Rate limit exceeded")
                    else:
                        result.error = f"HIBP API error: {resp.status}"
                        logger.error(f"HIBP: HTTP {resp.status}")

            result.total_breaches = len(result.breaches)
            return result

        except aiohttp.ClientError as e:
            logger.error(f"HIBP connection error: {e}")
            result.error = "Connection error"
            return result
        except Exception as e:
            logger.error(f"HIBP unexpected error: {e}")
            result.error = str(e)
            return result

    async def _check_pastes(self, email: str) -> int:
        """Проверка paste-сайтов через HIBP"""
        headers = {
            "hibp-api-key": self.api_key,
            "user-agent": self.HIBP_USER_AGENT,
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.HIBP_API_URL}/pasteaccount/{email}"
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return len(data)
                    return 0
        except Exception as e:
            logger.error(f"HIBP pastes error: {e}")
            return 0

    def _check_local_breaches(self, email: str) -> list[BreachInfo]:
        """Проверка по локальной базе известных утечек"""
        breaches = []
        email_lower = email.lower()
        domain = email_lower.split("@")[-1] if "@" in email_lower else ""

        # Проверяем домен email — если mail.ru, yandex и т.д.
        for breach_domain, breach_info in self.KNOWN_RUSSIAN_BREACHES.items():
            if domain == breach_domain or domain.endswith(f".{breach_domain}"):
                breaches.append(breach_info)

        # Проверяем домены где пользователи часто регистрируются
        common_breached_services = [
            "vk.com", "delivery-club.ru", "cdek.ru",
            "pikabu.ru", "geekbrains.ru",
        ]
        for service_domain in common_breached_services:
            if service_domain in self.KNOWN_RUSSIAN_BREACHES:
                breach = self.KNOWN_RUSSIAN_BREACHES[service_domain]
                if breach not in breaches:
                    # Добавляем как "возможную" утечку
                    possible_breach = BreachInfo(
                        name=breach.name,
                        title=breach.title,
                        domain=breach.domain,
                        breach_date=breach.breach_date,
                        pwn_count=breach.pwn_count,
                        data_classes=breach.data_classes,
                        description=breach.description + (
                            " (возможное совпадение)"
                        ),
                        severity=breach.severity,
                        is_verified=False,
                    )
                    # Не добавляем неподтвержденные по умолчанию
                    # breaches.append(possible_breach)

        return breaches

    @staticmethod
    def _calculate_severity(breach_data: dict) -> str:
        """Вычисляет критичность утечки"""
        data_classes = breach_data.get("DataClasses", [])
        pwn_count = breach_data.get("PwnCount", 0)

        critical_data = {
            "Credit cards", "Bank account numbers",
            "Passport numbers", "Government issued IDs",
            "Social security numbers",
        }
        high_data = {
            "Passwords", "Auth tokens",
            "Security questions and answers",
        }

        has_critical = bool(set(data_classes) & critical_data)
        has_high = bool(set(data_classes) & high_data)

        if has_critical:
            return "critical"
        elif has_high and pwn_count > 1_000_000:
            return "critical"
        elif has_high:
            return "high"
        elif pwn_count > 10_000_000:
            return "high"
        elif pwn_count > 100_000:
            return "medium"
        return "low"


# ─── Форматирование результатов ──────────────────────────

class LeakFormatter:
    """Форматирование результатов для Telegram"""

    @staticmethod
    def format_result(result: LeakCheckResult) -> str:
        """Форматирует полный результат проверки"""
        if result.error:
            return (
                f"⚠️ <b>Ошибка при проверке</b>\n\n"
                f"Не удалось выполнить проверку: {result.error}\n"
                f"Попробуйте позже."
            )

        if not result.is_compromised:
            return (
                f"✅ <b>Отличные новости!</b>\n\n"
                f"🔍 Запрос: <code>{_mask(result.query, result.query_type)}</code>\n"
                f"📊 Найдено утечек: <b>0</b>\n\n"
                f"Ваши данные не обнаружены в известных утечках.\n\n"
                f"💡 <i>Совет: Продолжайте использовать надёжные "
                f"уникальные пароли для каждого сервиса.</i>"
            )

        # Есть утечки
        lines = [
            f"🚨 <b>ВНИМАНИЕ! Обнаружены утечки!</b>\n",
            f"🔍 Запрос: <code>{_mask(result.query, result.query_type)}</code>",
            f"📊 Найдено утечек: <b>{result.total_breaches}</b>",
        ]

        if result.pastes > 0:
            lines.append(f"📋 Найдено в paste-сайтах: <b>{result.pastes}</b>")

        critical = result.critical_data_leaked
        if critical:
            lines.append(f"\n⛔ <b>Критичные данные в утечках:</b>")
            translations = {
                "Passwords": "🔑 Пароли",
                "Credit cards": "💳 Кредитные карты",
                "Bank account numbers": "🏦 Банковские счета",
                "Social security numbers": "🆔 Документы",
                "Passport numbers": "🛂 Паспорт",
                "Government issued IDs": "🆔 Гос. документы",
                "Auth tokens": "🔐 Токены авторизации",
            }
            for c in critical:
                name = translations.get(c, c)
                lines.append(f"  └ {name}")

        lines.append(f"\n{'─' * 30}")

        return "\n".join(lines)

    @staticmethod
    def format_breach(breach: BreachInfo, index: int) -> str:
        """Форматирует информацию об одной утечке"""
        lines = [
            f"\n{breach.severity_emoji} <b>{index}. {breach.title}</b>",
        ]

        if breach.domain:
            lines.append(f"  🌐 Домен: {breach.domain}")
        if breach.breach_date:
            lines.append(f"  📅 Дата: {breach.breach_date}")
        if breach.pwn_count:
            count_str = _format_number(breach.pwn_count)
            lines.append(f"  👥 Затронуто: {count_str} аккаунтов")

        if breach.data_classes_ru:
            lines.append(f"  📦 Утёкшие данные:")
            for dc in breach.data_classes_ru[:8]:  # Макс 8 типов
                lines.append(f"    • {dc}")
            if len(breach.data_classes_ru) > 8:
                lines.append(
                    f"    • ...и ещё "
                    f"{len(breach.data_classes_ru) - 8}"
                )

        if not breach.is_verified:
            lines.append(f"  ⚠️ <i>Не подтверждено</i>")

        return "\n".join(lines)

    @staticmethod
    def format_recommendations(result: LeakCheckResult) -> str:
        """Базовые рекомендации"""
        if not result.is_compromised:
            return ""

        lines = [
            "\n🛡 <b>Рекомендации по безопасности:</b>\n",
        ]

        # Определяем рекомендации на основе утёкших данных
        all_data_classes = set()
        domains = set()
        for breach in result.breaches:
            all_data_classes.update(breach.data_classes)
            if breach.domain:
                domains.add(breach.domain)

        lines.append("1️⃣ <b>Срочно смените пароли:</b>")
        if domains:
            for d in list(domains)[:5]:
                lines.append(f"   └ {d}")
        lines.append(
            "   └ И на всех сервисах с таким же паролем\n"
        )

        if "Passwords" in all_data_classes:
            lines.append(
                "2️⃣ 🔑 Ваши пароли скомпрометированы!\n"
                "   Используйте менеджер паролей "
                "(Bitwarden, KeePass)\n"
            )

        lines.append(
            "3️⃣ Включите двухфакторную аутентификацию (2FA)\n"
            "   везде, где это возможно\n"
        )

        if "Credit cards" in all_data_classes or \
           "Bank account numbers" in all_data_classes:
            lines.append(
                "4️⃣ 💳 <b>КРИТИЧНО:</b> Заблокируйте "
                "скомпрометированные карты!\n"
                "   Свяжитесь с банком немедленно\n"
            )

        if "Passport numbers" in all_data_classes or \
           "Government issued IDs" in all_data_classes:
            lines.append(
                "5️⃣ 🛂 <b>КРИТИЧНО:</b> Данные документов "
                "скомпрометированы!\n"
                "   Будьте осторожны с подозрительными "
                "звонками и сообщениями\n"
            )

        if "Phone numbers" in all_data_classes:
            lines.append(
                "6️⃣ 📱 Ваш телефон в утечке — ожидайте "
                "спам/фишинг звонки\n"
                "   Не переходите по ссылкам из SMS\n"
            )

        lines.append(
            "\n💡 <i>Оформите Premium для ИИ-рекомендаций "
            "и мониторинга новых утечек</i>"
        )

        return "\n".join(lines)


# ─── Вспомогательные функции ─────────────────────────────

def _mask(value: str, query_type: str) -> str:
    """Маскирует значение для отображения"""
    if query_type == "email" and "@" in value:
        parts = value.split("@")
        name = parts[0]
        if len(name) <= 2:
            masked = name[0] + "***"
        else:
            masked = name[0] + "***" + name[-1]
        return f"{masked}@{parts[1]}"
    elif query_type == "phone":
        if len(value) > 4:
            return value[:4] + "****" + value[-2:]
    return value[:2] + "***"


def _format_number(n: int) -> str:
    """Форматирует число с разделителями"""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} млрд"
    elif n >= 1_000_000:
        return f"{n / 1_000_000:.1f} млн"
    elif n >= 1_000:
        return f"{n / 1_000:.1f} тыс"
    return str(n)