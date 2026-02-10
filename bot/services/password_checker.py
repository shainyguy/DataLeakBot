"""
Сервис проверки паролей на стойкость и компрометацию.

1. Проверка по HIBP Pwned Passwords (k-anonymity)
2. Анализ стойкости пароля
3. Рекомендации по улучшению
"""

import aiohttp
import hashlib
import math
import re
import string
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PasswordCheckResult:
    """Результат проверки пароля"""
    # Компрометация
    is_compromised: bool = False
    times_seen: int = 0

    # Стойкость
    score: int = 0  # 0-100
    strength: str = "unknown"  # terrible, weak, fair, strong, excellent
    crack_time_display: str = ""
    entropy_bits: float = 0.0

    # Анализ
    length: int = 0
    has_upper: bool = False
    has_lower: bool = False
    has_digits: bool = False
    has_special: bool = False
    has_unicode: bool = False
    is_common_pattern: bool = False
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def strength_emoji(self) -> str:
        return {
            "terrible": "🔴",
            "weak": "🟠",
            "fair": "🟡",
            "strong": "🟢",
            "excellent": "💚",
        }.get(self.strength, "⚪")

    @property
    def strength_ru(self) -> str:
        return {
            "terrible": "Ужасный",
            "weak": "Слабый",
            "fair": "Средний",
            "strong": "Надёжный",
            "excellent": "Отличный",
        }.get(self.strength, "Неизвестно")

    @property
    def score_bar(self) -> str:
        """Визуальная шкала стойкости"""
        filled = self.score // 10
        empty = 10 - filled
        if self.score < 30:
            char = "🔴"
        elif self.score < 60:
            char = "🟡"
        else:
            char = "🟢"
        return char * filled + "⚪" * empty


class PasswordCheckerService:
    """Сервис проверки паролей"""

    # Топ-100 популярных паролей (часть)
    COMMON_PASSWORDS = {
        "password", "123456", "12345678", "qwerty", "abc123",
        "monkey", "1234567", "letmein", "trustno1", "dragon",
        "baseball", "iloveyou", "master", "sunshine", "ashley",
        "michael", "shadow", "123123", "654321", "superman",
        "qazwsx", "football", "password1", "password123",
        "000000", "111111", "1234", "12345", "123456789",
        "1234567890", "qwerty123", "1q2w3e4r", "admin", "root",
        "welcome", "access", "login", "passw0rd", "hello",
        "charlie", "donald", "loveme", "starwars", "solo",
        "princess", "hottie", "lovely", "test", "default",
        # Русские популярные
        "пароль", "йцукен", "привет", "любовь", "наташа",
        "максим", "андрей", "гандон", "сергей", "россия",
    }

    COMMON_PATTERNS = [
        r"^[a-z]+\d{1,4}$",          # word123
        r"^\d{6,}$",                    # 123456
        r"^[a-z]{1,3}\d{1,3}[a-z]{1,3}$",  # ab1cd
        r"^(.)\1+$",                    # aaaa
        r"^(01|12|23|34|45|56|67|78|89|90)+$",  # Последовательности
        r"^(qwerty|asdfgh|zxcvbn)",     # Клавиатурные
        r"^(йцукен|фывапр|ячсмит)",     # Клавиатурные RU
    ]

    KEYBOARD_SEQUENCES = [
        "qwerty", "qwertyuiop", "asdfghjkl", "zxcvbnm",
        "1234567890", "qazwsx", "1qaz2wsx",
        "йцукен", "фывапр", "ячсмит",
    ]

    async def check_password(self, password: str) -> PasswordCheckResult:
        """Полная проверка пароля"""
        result = PasswordCheckResult()

        # 1. Базовый анализ
        result.length = len(password)
        result.has_upper = bool(re.search(r"[A-ZА-ЯЁ]", password))
        result.has_lower = bool(re.search(r"[a-zа-яё]", password))
        result.has_digits = bool(re.search(r"\d", password))
        result.has_special = bool(
            re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password)
        )
        result.has_unicode = bool(re.search(r"[^\x00-\x7F]", password))

        # 2. Проверка на известные шаблоны
        result.is_common_pattern = self._check_common_patterns(password)

        # 3. Энтропия
        result.entropy_bits = self._calculate_entropy(password)

        # 4. Время взлома
        result.crack_time_display = self._estimate_crack_time(
            result.entropy_bits
        )

        # 5. Общий скор
        result.score = self._calculate_score(password, result)

        # 6. Уровень стойкости
        result.strength = self._get_strength_level(result.score)

        # 7. Предупреждения и советы
        result.warnings, result.suggestions = self._generate_feedback(
            password, result
        )

        # 8. Проверка по HIBP Pwned Passwords
        pwned = await self._check_hibp_passwords(password)
        result.is_compromised = pwned > 0
        result.times_seen = pwned

        if result.is_compromised:
            result.warnings.insert(
                0,
                f"⛔ Пароль найден в {_fmt_num(pwned)} утечках!",
            )
            result.score = max(0, result.score - 40)
            if result.score < 20:
                result.strength = "terrible"

        return result

    async def _check_hibp_passwords(self, password: str) -> int:
        """
        Проверка пароля по HIBP Pwned Passwords.
        Использует k-anonymity: отправляется только
        первые 5 символов SHA-1 хеша.
        """
        sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix = sha1[:5]
        suffix = sha1[5:]

        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.pwnedpasswords.com/range/{prefix}"
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        for line in text.splitlines():
                            parts = line.strip().split(":")
                            if len(parts) == 2:
                                if parts[0].upper() == suffix:
                                    return int(parts[1])
                        return 0
                    return 0
        except Exception as e:
            logger.error(f"HIBP Passwords check error: {e}")
            return 0

    def _check_common_patterns(self, password: str) -> bool:
        """Проверка на типичные слабые шаблоны"""
        pwd_lower = password.lower()

        if pwd_lower in self.COMMON_PASSWORDS:
            return True

        for seq in self.KEYBOARD_SEQUENCES:
            if seq in pwd_lower:
                return True

        for pattern in self.COMMON_PATTERNS:
            if re.match(pattern, pwd_lower):
                return True

        # Проверка повторений
        if len(set(password)) <= 2 and len(password) > 3:
            return True

        return False

    def _calculate_entropy(self, password: str) -> float:
        """Вычисляет энтропию пароля в битах"""
        charset_size = 0

        if re.search(r"[a-z]", password):
            charset_size += 26
        if re.search(r"[A-Z]", password):
            charset_size += 26
        if re.search(r"\d", password):
            charset_size += 10
        if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            charset_size += 32
        if re.search(r"[а-яё]", password, re.IGNORECASE):
            charset_size += 66
        if re.search(r"[^\x00-\x7Fа-яА-ЯёЁ]", password):
            charset_size += 100

        if charset_size == 0:
            charset_size = 1

        entropy = len(password) * math.log2(charset_size)

        # Штраф за повторения
        unique_ratio = len(set(password)) / len(password) if password else 0
        entropy *= max(0.5, unique_ratio)

        return round(entropy, 1)

    def _estimate_crack_time(self, entropy_bits: float) -> str:
        """Оценка времени взлома при 10 млрд попыток/сек"""
        guesses_per_sec = 10_000_000_000  # 10 GH/s (GPU)
        total_guesses = 2 ** entropy_bits
        seconds = total_guesses / guesses_per_sec

        if seconds < 0.001:
            return "мгновенно"
        elif seconds < 1:
            return f"{seconds * 1000:.0f} мс"
        elif seconds < 60:
            return f"{seconds:.0f} сек"
        elif seconds < 3600:
            return f"{seconds / 60:.0f} мин"
        elif seconds < 86400:
            return f"{seconds / 3600:.0f} часов"
        elif seconds < 86400 * 30:
            return f"{seconds / 86400:.0f} дней"
        elif seconds < 86400 * 365:
            return f"{seconds / (86400 * 30):.0f} месяцев"
        elif seconds < 86400 * 365 * 100:
            return f"{seconds / (86400 * 365):.0f} лет"
        elif seconds < 86400 * 365 * 1_000_000:
            return f"{seconds / (86400 * 365 * 1000):.0f} тыс. лет"
        elif seconds < 86400 * 365 * 1_000_000_000:
            return f"{seconds / (86400 * 365 * 1_000_000):.0f} млн лет"
        else:
            return "∞ (тепловая смерть вселенной)"

    def _calculate_score(
        self, password: str, result: PasswordCheckResult
    ) -> int:
        """Вычисляет общий скор 0-100"""
        score = 0

        # Длина (до 30 баллов)
        length = len(password)
        if length >= 16:
            score += 30
        elif length >= 12:
            score += 25
        elif length >= 10:
            score += 20
        elif length >= 8:
            score += 15
        elif length >= 6:
            score += 10
        else:
            score += 5

        # Разнообразие символов (до 30 баллов)
        char_types = sum([
            result.has_upper, result.has_lower,
            result.has_digits, result.has_special,
        ])
        score += char_types * 7 + (3 if result.has_unicode else 0)

        # Энтропия (до 25 баллов)
        if result.entropy_bits >= 80:
            score += 25
        elif result.entropy_bits >= 60:
            score += 20
        elif result.entropy_bits >= 40:
            score += 15
        elif result.entropy_bits >= 25:
            score += 10
        else:
            score += 5

        # Уникальность символов (до 15 баллов)
        if password:
            unique_ratio = len(set(password)) / len(password)
            score += int(unique_ratio * 15)

        # Штрафы
        if result.is_common_pattern:
            score -= 30
        if length < 6:
            score -= 20

        return max(0, min(100, score))

    def _get_strength_level(self, score: int) -> str:
        if score < 20:
            return "terrible"
        elif score < 40:
            return "weak"
        elif score < 60:
            return "fair"
        elif score < 80:
            return "strong"
        return "excellent"

    def _generate_feedback(
        self, password: str, result: PasswordCheckResult
    ) -> tuple[list[str], list[str]]:
        """Генерирует предупреждения и советы"""
        warnings = []
        suggestions = []

        if result.length < 8:
            warnings.append("⚠️ Пароль слишком короткий")
            suggestions.append("Используйте минимум 12 символов")

        if not result.has_upper:
            suggestions.append("Добавьте заглавные буквы (A-Z)")
        if not result.has_lower:
            suggestions.append("Добавьте строчные буквы (a-z)")
        if not result.has_digits:
            suggestions.append("Добавьте цифры (0-9)")
        if not result.has_special:
            suggestions.append("Добавьте спецсимволы (!@#$%^&*)")

        if result.is_common_pattern:
            warnings.append("⚠️ Пароль основан на известном шаблоне")
            suggestions.append(
                "Не используйте словарные слова и "
                "клавиатурные последовательности"
            )

        pwd_lower = password.lower()
        if pwd_lower in self.COMMON_PASSWORDS:
            warnings.append("⛔ Входит в топ самых популярных паролей!")

        if len(set(password)) <= 3:
            warnings.append("⚠️ Слишком мало уникальных символов")

        if not suggestions:
            suggestions.append("✅ Пароль выглядит надёжным!")

        return warnings, suggestions


# ─── Форматирование ──────────────────────────────────────

class PasswordFormatter:
    """Форматирование результатов проверки пароля"""

    @staticmethod
    def format_result(result: PasswordCheckResult) -> str:
        lines = [
            f"🔑 <b>Анализ пароля</b>\n",
            f"📊 Стойкость: {result.strength_emoji} "
            f"<b>{result.strength_ru}</b>",
            f"📈 Оценка: {result.score}/100",
            f"{result.score_bar}\n",
            f"📐 Длина: {result.length} символов",
            f"🔐 Энтропия: {result.entropy_bits} бит",
            f"⏱ Время взлома: <b>{result.crack_time_display}</b>\n",
        ]

        # Состав пароля
        lines.append("📋 <b>Состав пароля:</b>")
        checks = [
            (result.has_upper, "Заглавные буквы"),
            (result.has_lower, "Строчные буквы"),
            (result.has_digits, "Цифры"),
            (result.has_special, "Спецсимволы"),
        ]
        for has, name in checks:
            icon = "✅" if has else "❌"
            lines.append(f"  {icon} {name}")

        # Компрометация
        if result.is_compromised:
            lines.append(
                f"\n⛔ <b>ПАРОЛЬ СКОМПРОМЕТИРОВАН!</b>"
            )
            lines.append(
                f"Найден в <b>{_fmt_num(result.times_seen)}</b> утечках"
            )
            lines.append(
                "🚫 <b>Немедленно смените этот пароль везде!</b>"
            )
        else:
            lines.append(
                "\n✅ Пароль не найден в известных утечках"
            )

        # Предупреждения
        if result.warnings:
            lines.append(f"\n⚠️ <b>Предупреждения:</b>")
            for w in result.warnings:
                lines.append(f"  {w}")

        # Советы
        if result.suggestions:
            lines.append(f"\n💡 <b>Рекомендации:</b>")
            for s in result.suggestions:
                lines.append(f"  • {s}")

        lines.append(
            "\n🔒 <i>Мы не сохраняем ваши пароли. "
            "Проверка безопасна (k-anonymity).</i>"
        )

        return "\n".join(lines)


def _fmt_num(n: int) -> str:
    """Форматирование числа с разделителями"""
    return f"{n:,}".replace(",", " ")