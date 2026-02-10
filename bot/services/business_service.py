"""
Бизнес-сервис: мониторинг корпоративных доменов.
Проверяет все email @company.com по базам утечек.
"""

import aiohttp
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class DomainScanResult:
    """Результат сканирования домена"""
    domain: str
    breaches: list[dict] = field(default_factory=list)
    total_breaches: int = 0
    total_emails_exposed: int = 0
    data_types_exposed: list[str] = field(default_factory=list)
    error: str | None = None
    scanned_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class BusinessService:
    """Корпоративный мониторинг"""

    HIBP_API_URL = "https://haveibeenpwned.com/api/v3"

    def __init__(self):
        self.api_key = settings.hibp_api_key

    async def scan_domain(self, domain: str) -> DomainScanResult:
        """
        Сканирование домена через HIBP API.
        HIBP поддерживает поиск breaches по домену.
        """
        result = DomainScanResult(domain=domain)

        if not self.api_key:
            result.error = "API key not configured"
            return result

        try:
            breaches = await self._get_domain_breaches(domain)
            result.breaches = breaches
            result.total_breaches = len(breaches)

            all_data_types = set()
            total_accounts = 0
            for breach in breaches:
                all_data_types.update(
                    breach.get("DataClasses", [])
                )
                total_accounts += breach.get("PwnCount", 0)

            result.total_emails_exposed = total_accounts
            result.data_types_exposed = list(all_data_types)

        except Exception as e:
            logger.error(f"Domain scan error for {domain}: {e}")
            result.error = str(e)

        return result

    async def _get_domain_breaches(
        self, domain: str
    ) -> list[dict]:
        """Получить утечки для домена через HIBP"""
        headers = {
            "hibp-api-key": self.api_key,
            "user-agent": "DataLeakBot-Business",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # HIBP breaches endpoint
                url = f"{self.HIBP_API_URL}/breaches"
                params = {"domain": domain}

                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 404:
                        return []
                    else:
                        logger.error(
                            f"HIBP domain API: {resp.status}"
                        )
                        return []

        except Exception as e:
            logger.error(f"HIBP domain request error: {e}")
            return []

    @staticmethod
    def format_domain_report(result: DomainScanResult) -> str:
        """Формирует текстовый отчёт"""
        if result.error:
            return (
                f"❌ <b>Ошибка сканирования</b>\n"
                f"Домен: {result.domain}\n"
                f"Ошибка: {result.error}"
            )

        if result.total_breaches == 0:
            return (
                f"🏢 <b>Отчёт: {result.domain}</b>\n\n"
                f"✅ Домен не найден в известных утечках!\n\n"
                f"📅 Сканирование: "
                f"{result.scanned_at.strftime('%d.%m.%Y %H:%M')}"
            )

        lines = [
            f"🏢 <b>Корпоративный отчёт: {result.domain}</b>\n",
            f"🚨 Найдено утечек: <b>{result.total_breaches}</b>",
            f"👥 Затронуто записей: <b>"
            f"{result.total_emails_exposed:,}</b>".replace(",", " "),
            "",
        ]

        # Типы утёкших данных
        if result.data_types_exposed:
            lines.append("📦 <b>Типы утёкших данных:</b>")
            data_translations = {
                "Passwords": "🔑 Пароли",
                "Email addresses": "📧 Email",
                "Phone numbers": "📱 Телефоны",
                "Names": "👤 Имена",
                "Physical addresses": "📍 Адреса",
                "Credit cards": "💳 Карты",
                "Dates of birth": "🎂 Даты рождения",
            }
            for dt in result.data_types_exposed[:10]:
                translated = data_translations.get(dt, f"📄 {dt}")
                lines.append(f"  • {translated}")

        lines.append("")

        # Список утечек
        lines.append("📋 <b>Утечки:</b>")
        for i, breach in enumerate(result.breaches[:10], 1):
            name = breach.get("Title", breach.get("Name", "?"))
            date = breach.get("BreachDate", "?")
            count = breach.get("PwnCount", 0)
            count_str = f"{count:,}".replace(",", " ")
            lines.append(
                f"  {i}. <b>{name}</b> — {date} "
                f"({count_str} записей)"
            )

        if len(result.breaches) > 10:
            lines.append(
                f"  ...и ещё {len(result.breaches) - 10}"
            )

        lines.extend([
            "",
            f"📅 Сканирование: "
            f"{result.scanned_at.strftime('%d.%m.%Y %H:%M')}",
            "",
            "🛡 <b>Рекомендации для компании:</b>",
            "1. Принудительная смена паролей сотрудников",
            "2. Внедрение 2FA для всех аккаунтов",
            "3. Аудит доступов к корп. системам",
            "4. Обучение сотрудников InfoSec",
            "5. Проверка на фишинговые атаки",
        ])

        return "\n".join(lines)

    @staticmethod
    def format_executive_report(
        result: DomainScanResult,
        company_name: str = "",
    ) -> str:
        """Отчёт для руководства (краткий)"""
        company = company_name or result.domain
        risk_level = "🟢 НИЗКИЙ"

        if result.total_breaches > 5:
            risk_level = "🔴 ВЫСОКИЙ"
        elif result.total_breaches > 2:
            risk_level = "🟠 СРЕДНИЙ"
        elif result.total_breaches > 0:
            risk_level = "🟡 УМЕРЕННЫЙ"

        has_passwords = "Passwords" in result.data_types_exposed
        has_cards = "Credit cards" in result.data_types_exposed

        lines = [
            f"📊 <b>ОТЧЁТ ДЛЯ РУКОВОДСТВА</b>",
            f"🏢 Компания: {company}",
            f"🌐 Домен: {result.domain}",
            f"📅 Дата: "
            f"{result.scanned_at.strftime('%d.%m.%Y')}\n",
            f"{'═' * 30}",
            f"⚡ Уровень риска: {risk_level}",
            f"🚨 Утечек: {result.total_breaches}",
            f"👥 Записей скомпрометировано: "
            f"{result.total_emails_exposed:,}".replace(",", " "),
            f"{'═' * 30}\n",
        ]

        if has_passwords:
            lines.append(
                "⚠️ КРИТИЧНО: Пароли сотрудников "
                "обнаружены в утечках!"
            )
        if has_cards:
            lines.append(
                "⚠️ КРИТИЧНО: Данные карт "
                "обнаружены в утечках!"
            )

        lines.extend([
            "",
            "📌 <b>Ключевые действия:</b>",
            "1. Немедленный сброс паролей",
            "2. Аудит безопасности",
            "3. Уведомление затронутых сотрудников",
        ])

        return "\n".join(lines)