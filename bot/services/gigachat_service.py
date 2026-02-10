"""
Сервис GigaChat для ИИ-рекомендаций по безопасности.
"""

import logging
from config import settings

logger = logging.getLogger(__name__)

# Пробуем импортировать GigaChat
try:
    from gigachat import GigaChat
    from gigachat.models import Chat, Messages, MessagesRole

    GIGACHAT_AVAILABLE = True
except ImportError:
    GIGACHAT_AVAILABLE = False
    logger.warning("GigaChat library not installed")


class GigaChatService:
    """Сервис ИИ-рекомендаций через GigaChat"""

    SYSTEM_PROMPT = """Ты — эксперт по кибербезопасности и защите персональных данных.
Ты работаешь в телеграм-боте DataLeakBot, который проверяет утечки данных.

Твои задачи:
1. Давать персонализированные рекомендации по безопасности
2. Объяснять риски утечек простым языком
3. Предлагать конкретные шаги по защите
4. Рекомендовать инструменты (менеджеры паролей, VPN, 2FA)

Правила:
- Отвечай на русском языке
- Будь конкретным и практичным
- Используй эмодзи для структуры
- Не пугай, но объясняй реальные риски
- Ответ до 500 слов
- Учитывай российскую специфику (Госуслуги, банки РФ)"""

    def __init__(self):
        self.available = GIGACHAT_AVAILABLE and bool(settings.gigachat_api_key)
        self.client = None

        if self.available:
            try:
                self.client = GigaChat(
                    credentials=settings.gigachat_api_key,
                    verify_ssl_certs=False,
                )
            except Exception as e:
                logger.error(f"GigaChat init error: {e}")
                self.available = False

    async def get_leak_recommendations(
        self,
        breaches: list[dict],
        email_domain: str = "",
    ) -> str:
        """Получить ИИ-рекомендации по утечкам"""
        if not self.available:
            return self._fallback_recommendations(breaches)

        # Формируем контекст для GigaChat
        breach_summary = []
        all_data_types = set()

        for b in breaches[:10]:  # Максимум 10
            breach_summary.append(
                f"- {b.get('title', 'Unknown')}: "
                f"дата {b.get('breach_date', '?')}, "
                f"данные: {', '.join(b.get('data_classes', []))}"
            )
            all_data_types.update(b.get("data_classes", []))

        prompt = f"""Пользователь проверил свой email и обнаружены следующие утечки данных:

{chr(10).join(breach_summary)}

Всего утечек: {len(breaches)}
Утёкшие типы данных: {', '.join(all_data_types)}
{'Домен email: ' + email_domain if email_domain else ''}

Дай персональные рекомендации:
1. Оцени уровень угрозы (низкий/средний/высокий/критический)
2. Какие конкретные шаги предпринять СЕЙЧАС
3. Какие сервисы/аккаунты под угрозой
4. Долгосрочные рекомендации по защите
5. Какие инструменты использовать"""

        try:
            response = self.client.chat(
                Chat(
                    messages=[
                        Messages(
                            role=MessagesRole.SYSTEM,
                            content=self.SYSTEM_PROMPT,
                        ),
                        Messages(
                            role=MessagesRole.USER,
                            content=prompt,
                        ),
                    ],
                    temperature=0.7,
                    max_tokens=1024,
                )
            )
            return (
                "🤖 <b>ИИ-анализ безопасности (GigaChat):</b>\n\n"
                + response.choices[0].message.content
            )

        except Exception as e:
            logger.error(f"GigaChat error: {e}")
            return self._fallback_recommendations(breaches)

    async def get_password_advice(
        self,
        score: int,
        strength: str,
        is_compromised: bool,
        warnings: list[str],
    ) -> str:
        """ИИ-советы по паролю"""
        if not self.available:
            return ""

        prompt = f"""Пользователь проверил свой пароль. Результаты:
- Оценка стойкости: {score}/100 ({strength})
- Скомпрометирован: {"Да" if is_compromised else "Нет"}
- Предупреждения: {'; '.join(warnings) if warnings else 'нет'}

Дай краткие (3-5 пунктов) практические советы по созданию и управлению паролями.
Учитывай российские реалии."""

        try:
            response = self.client.chat(
                Chat(
                    messages=[
                        Messages(
                            role=MessagesRole.SYSTEM,
                            content=self.SYSTEM_PROMPT,
                        ),
                        Messages(
                            role=MessagesRole.USER,
                            content=prompt,
                        ),
                    ],
                    temperature=0.7,
                    max_tokens=512,
                )
            )
            return (
                "\n\n🤖 <b>Совет от ИИ:</b>\n"
                + response.choices[0].message.content
            )

        except Exception as e:
            logger.error(f"GigaChat password advice error: {e}")
            return ""

    async def answer_security_question(self, question: str) -> str:
        """Ответ на вопрос по безопасности"""
        if not self.available:
            return (
                "🤖 ИИ-ассистент временно недоступен. "
                "Попробуйте позже."
            )

        try:
            response = self.client.chat(
                Chat(
                    messages=[
                        Messages(
                            role=MessagesRole.SYSTEM,
                            content=self.SYSTEM_PROMPT,
                        ),
                        Messages(
                            role=MessagesRole.USER,
                            content=question,
                        ),
                    ],
                    temperature=0.7,
                    max_tokens=768,
                )
            )
            return (
                "🤖 <b>Ответ ИИ-ассистента:</b>\n\n"
                + response.choices[0].message.content
            )

        except Exception as e:
            logger.error(f"GigaChat question error: {e}")
            return "❌ Произошла ошибка. Попробуйте позже."

    @staticmethod
    def _fallback_recommendations(breaches: list[dict]) -> str:
        """Рекомендации без ИИ"""
        all_data = set()
        for b in breaches:
            all_data.update(b.get("data_classes", []))

        lines = [
            "🛡 <b>Рекомендации по безопасности:</b>\n",
            "1️⃣ <b>Немедленно смените пароли</b> на всех "
            "скомпрометированных сервисах",
            "",
            "2️⃣ <b>Включите двухфакторную аутентификацию</b> "
            "(2FA) везде, где возможно:",
            "  • Госуслуги",
            "  • Банковские приложения",
            "  • Почта (Mail.ru, Яндекс)",
            "  • Соцсети (VK, Telegram)",
            "",
            "3️⃣ <b>Используйте менеджер паролей:</b>",
            "  • Bitwarden (бесплатный)",
            "  • KeePass (оффлайн)",
            "",
            "4️⃣ <b>Создавайте уникальные пароли</b> "
            "для каждого сервиса (мин. 12 символов)",
        ]

        if "Passwords" in all_data:
            lines.extend([
                "",
                "⚠️ <b>Ваши пароли утекли!</b> Смените их "
                "на ВСЕХ сервисах, где использовался "
                "такой же пароль",
            ])

        if "Phone numbers" in all_data:
            lines.extend([
                "",
                "📱 <b>Телефон скомпрометирован:</b>",
                "  • Не отвечайте на незнакомые звонки",
                "  • Не переходите по ссылкам из SMS",
                "  • Не сообщайте коды из SMS никому",
            ])

        if "Credit cards" in all_data:
            lines.extend([
                "",
                "💳 <b>СРОЧНО:</b> Свяжитесь с банком "
                "и перевыпустите карту!",
            ])

        return "\n".join(lines)