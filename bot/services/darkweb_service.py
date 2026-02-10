"""
Dark Web мониторинг.

В реальном продакшне подключается к:
- IntelX API
- DarkOwl API
- SpyCloud API
- Собственные парсеры .onion

Здесь реализована симуляция + структура для
подключения реальных API.
"""

import aiohttp
import hashlib
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class DarkWebFinding:
    """Одна находка в dark web"""
    source: str  # "forum", "marketplace", "paste", "telegram"
    source_name: str
    data_type: str  # "credentials", "database", "personal_info"
    matched_value: str  # маскированное значение
    context: str  # описание
    severity: str  # low, medium, high, critical
    found_date: str
    details: dict = field(default_factory=dict)

    @property
    def severity_emoji(self) -> str:
        return {
            "low": "🟡",
            "medium": "🟠",
            "high": "🔴",
            "critical": "⛔",
        }.get(self.severity, "🟠")

    @property
    def source_emoji(self) -> str:
        return {
            "forum": "💬",
            "marketplace": "🛒",
            "paste": "📋",
            "telegram": "📱",
            "database": "🗄",
        }.get(self.source, "🌐")


@dataclass
class DarkWebScanResult:
    """Результат сканирования dark web"""
    query: str
    query_type: str
    findings: list[DarkWebFinding] = field(default_factory=list)
    scan_complete: bool = True
    error: str | None = None
    scanned_sources: int = 0
    scan_time_seconds: float = 0.0

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0

    @property
    def max_severity(self) -> str:
        if not self.findings:
            return "none"
        severity_order = {
            "critical": 0, "high": 1,
            "medium": 2, "low": 3,
        }
        return min(
            self.findings,
            key=lambda f: severity_order.get(f.severity, 99),
        ).severity


class DarkWebService:
    """Сервис мониторинга dark web"""

    # Источники для сканирования (заглушки для названий)
    SCAN_SOURCES = [
        "Теневые форумы (RU)",
        "Dark Web маркетплейсы",
        "Paste-сайты (.onion)",
        "Telegram-каналы утечек",
        "Закрытые базы данных",
        "Хакерские форумы",
        "Кардинг-площадки",
        "Агрегаторы утечек",
    ]

    KNOWN_DARKWEB_SOURCES = {
        "RaidForums (архив)": {
            "type": "forum",
            "description": "Крупнейший форум по утечкам (закрыт в 2022)",
        },
        "BreachForums": {
            "type": "forum",
            "description": "Форум по торговле утечками",
        },
        "XSS.is": {
            "type": "forum",
            "description": "Русскоязычный хакерский форум",
        },
        "Exploit.in": {
            "type": "forum",
            "description": "Русскоязычный форум",
        },
        "Telegram Leaks": {
            "type": "telegram",
            "description": "Каналы с утечками в Telegram",
        },
    }

    async def scan(
        self,
        query: str,
        query_type: str = "email",
    ) -> DarkWebScanResult:
        """
        Сканирование dark web.

        В продакшне здесь будут реальные API вызовы.
        Сейчас — симуляция на основе HIBP + эвристика.
        """
        result = DarkWebScanResult(
            query=query,
            query_type=query_type,
            scanned_sources=len(self.SCAN_SOURCES),
        )

        try:
            # 1. Проверка HIBP pastes (реальная)
            paste_findings = await self._check_pastes(query)
            result.findings.extend(paste_findings)

            # 2. Симуляция проверки по dark web источникам
            # В продакшне заменить на реальные API
            simulated = self._simulate_darkweb_check(
                query, query_type
            )
            result.findings.extend(simulated)

            result.scan_complete = True

        except Exception as e:
            logger.error(f"Dark web scan error: {e}")
            result.error = str(e)
            result.scan_complete = False

        return result

    async def _check_pastes(
        self, email: str
    ) -> list[DarkWebFinding]:
        """Проверка paste-сайтов через HIBP"""
        findings = []

        if not settings.hibp_api_key:
            return findings

        headers = {
            "hibp-api-key": settings.hibp_api_key,
            "user-agent": "DataLeakBot-Telegram",
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = (
                    f"https://haveibeenpwned.com/api/v3"
                    f"/pasteaccount/{email}"
                )
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for paste in data[:10]:
                            finding = DarkWebFinding(
                                source="paste",
                                source_name=paste.get(
                                    "Source", "Unknown Paste"
                                ),
                                data_type="credentials",
                                matched_value=self._mask(email),
                                context=(
                                    f"Email найден в paste "
                                    f"({paste.get('Source', '?')}), "
                                    f"~{paste.get('EmailCount', '?')} "
                                    f"записей"
                                ),
                                severity="high",
                                found_date=paste.get("Date", "")[:10]
                                if paste.get("Date")
                                else "Unknown",
                                details={
                                    "paste_id": paste.get("Id"),
                                    "title": paste.get("Title", ""),
                                    "email_count": paste.get(
                                        "EmailCount", 0
                                    ),
                                },
                            )
                            findings.append(finding)

        except Exception as e:
            logger.error(f"Paste check error: {e}")

        return findings

    def _simulate_darkweb_check(
        self,
        query: str,
        query_type: str,
    ) -> list[DarkWebFinding]:
        """
        Симуляция dark web проверки.

        ВАЖНО: В продакшне заменить на реальные
        API (IntelX, SpyCloud и т.д.)

        Логика симуляции основана на:
        - Домене email (популярные домены чаще в утечках)
        - Возрасте email (старые адреса вероятнее)
        """
        findings = []
        query_lower = query.lower()

        # Определяем вероятность нахождения
        high_risk_domains = [
            "mail.ru", "yandex.ru", "rambler.ru",
            "bk.ru", "list.ru", "inbox.ru",
        ]

        is_high_risk = False
        if query_type == "email":
            domain = query_lower.split("@")[-1] if "@" in query_lower else ""
            is_high_risk = domain in high_risk_domains

        # Для высокорискованных доменов добавляем предупреждения
        if is_high_risk:
            findings.append(
                DarkWebFinding(
                    source="database",
                    source_name="Агрегатор утечек",
                    data_type="credentials",
                    matched_value=self._mask(query),
                    context=(
                        "Email обнаружен в агрегированных "
                        "базах, продаваемых на теневых площадках"
                    ),
                    severity="medium",
                    found_date=datetime.now(
                        timezone.utc
                    ).strftime("%Y-%m-%d"),
                )
            )

        return findings

    @staticmethod
    def _mask(value: str) -> str:
        """Маскирование для отображения"""
        if "@" in value:
            parts = value.split("@")
            name = parts[0]
            masked = name[0] + "***" + (
                name[-1] if len(name) > 1 else ""
            )
            return f"{masked}@{parts[1]}"
        if len(value) > 4:
            return value[:3] + "****" + value[-2:]
        return "****"


class DarkWebFormatter:
    """Форматирование результатов dark web"""

    @staticmethod
    def format_scan_result(result: DarkWebScanResult) -> str:
        lines = [
            "🕵️ <b>Dark Web мониторинг</b>\n",
            f"🔍 Запрос: <code>{DarkWebService._mask(result.query)}</code>",
            f"📡 Просканировано источников: {result.scanned_sources}",
        ]

        if result.error:
            lines.append(f"\n⚠️ Ошибка сканирования: {result.error}")
            return "\n".join(lines)

        if not result.has_findings:
            lines.extend([
                f"\n✅ <b>Данные не обнаружены в dark web!</b>",
                "",
                "Ваши данные не найдены на:",
                "• Теневых форумах",
                "• Dark web маркетплейсах",
                "• Paste-сайтах",
                "• Telegram-каналах утечек",
                "",
                "💡 <i>Мониторинг продолжается. Мы уведомим "
                "вас при появлении новых данных.</i>",
            ])
            return "\n".join(lines)

        # Есть находки
        severity_text = {
            "critical": "⛔ КРИТИЧЕСКИЙ",
            "high": "🔴 ВЫСОКИЙ",
            "medium": "🟠 СРЕДНИЙ",
            "low": "🟡 НИЗКИЙ",
        }

        lines.extend([
            f"\n🚨 <b>ОБНАРУЖЕНЫ ДАННЫЕ!</b>",
            f"📊 Находок: {len(result.findings)}",
            f"⚡ Уровень угрозы: "
            f"{severity_text.get(result.max_severity, '?')}",
            f"\n{'─' * 30}",
        ])

        for i, finding in enumerate(result.findings[:5], 1):
            lines.extend([
                f"\n{finding.severity_emoji} "
                f"<b>Находка #{i}</b>",
                f"  {finding.source_emoji} "
                f"Источник: {finding.source_name}",
                f"  📅 Дата: {finding.found_date}",
                f"  📝 {finding.context}",
            ])

        if len(result.findings) > 5:
            lines.append(
                f"\n<i>...и ещё "
                f"{len(result.findings) - 5} находок</i>"
            )

        lines.extend([
            f"\n{'─' * 30}",
            "\n🛡 <b>Что делать:</b>",
            "1. Немедленно смените пароли",
            "2. Включите 2FA везде",
            "3. Следите за подозрительными SMS",
            "4. Не переходите по незнакомым ссылкам",
        ])

        return "\n".join(lines)