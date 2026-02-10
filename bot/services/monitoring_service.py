"""
Фоновый сервис мониторинга утечек.
Периодически проверяет все email на мониторинге.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from database.engine import async_session
from database.crud import (
    MonitorCRUD,
    DarkWebCRUD,
    NotificationCRUD,
    UserCRUD,
)
from database.models import User, SubscriptionType
from bot.services.leak_checker import LeakCheckerService
from bot.services.darkweb_service import DarkWebService
from bot.utils.helpers import is_subscription_active
from sqlalchemy import select

logger = logging.getLogger(__name__)


class MonitoringService:
    """Сервис фонового мониторинга"""

    def __init__(self, bot=None):
        self.bot = bot
        self.leak_checker = LeakCheckerService()
        self.darkweb_service = DarkWebService()

    async def run_monitoring_cycle(self):
        """Один цикл мониторинга всех активных email"""
        logger.info("🔄 Starting monitoring cycle...")

        async with async_session() as session:
            monitored = await MonitorCRUD.get_all_active(session)
            logger.info(
                f"📊 Monitoring {len(monitored)} emails"
            )

            for entry in monitored:
                try:
                    await self._check_single(session, entry)
                    # Rate limiting — HIBP разрешает 1 req/1.5sec
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(
                        f"Error monitoring {entry.id}: {e}"
                    )

        logger.info("✅ Monitoring cycle complete")

    async def _check_single(
        self,
        session: AsyncSession,
        entry,
    ):
        """Проверка одного email"""
        # Получаем пользователя
        stmt = select(User).where(User.id == entry.user_id)
        result_q = await session.execute(stmt)
        user = result_q.scalar_one_or_none()

        if not user or not is_subscription_active(user):
            return

        # Проверяем утечки
        result = await self.leak_checker.check_email(entry.email)

        old_count = entry.last_breach_count
        new_count = result.total_breaches

        # Обновляем запись
        await MonitorCRUD.update_check_result(
            session, entry.id, new_count
        )

        # Новые утечки?
        if new_count > old_count:
            await self._notify_new_breach(
                session, user, entry.email, result, old_count
            )

    async def _notify_new_breach(
        self,
        session: AsyncSession,
        user: User,
        email: str,
        result,
        old_count: int,
    ):
        """Уведомление о новой утечке"""
        new_breaches = result.breaches[: result.total_breaches - old_count]

        # Проверяем, не отправляли ли уже
        content = f"{email}:{result.total_breaches}"
        content_hash = hashlib.sha256(
            content.encode()
        ).hexdigest()

        already_sent = await NotificationCRUD.was_sent(
            session, user.id, "new_breach", content_hash
        )
        if already_sent:
            return

        # Формируем сообщение
        breach_names = ", ".join(
            b.title for b in new_breaches[:3]
        )
        masked_email = self._mask_email(email)

        text = (
            f"🚨 <b>НОВАЯ УТЕЧКА ОБНАРУЖЕНА!</b>\n\n"
            f"📧 Email: <code>{masked_email}</code>\n"
            f"🆕 Новых утечек: "
            f"{result.total_breaches - old_count}\n"
            f"📊 Всего утечек: {result.total_breaches}\n\n"
            f"🔍 Сервисы: {breach_names}\n\n"
            f"🛡 <b>Рекомендации:</b>\n"
            f"1. Срочно смените пароль на этих сервисах\n"
            f"2. Включите 2FA\n"
            f"3. Проверьте подозрительную активность\n\n"
            f"Подробнее: /check"
        )

        # Отправляем
        if self.bot:
            try:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
                # Логируем
                await NotificationCRUD.log_sent(
                    session, user.id, "new_breach", content_hash
                )
                logger.info(
                    f"📤 Notified user {user.telegram_id} "
                    f"about new breach for {masked_email}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to notify {user.telegram_id}: {e}"
                )

    async def run_darkweb_cycle(self):
        """Цикл dark web мониторинга"""
        logger.info("🕵️ Starting dark web scan cycle...")

        async with async_session() as session:
            monitored = await MonitorCRUD.get_all_active(session)

            for entry in monitored:
                try:
                    stmt = select(User).where(
                        User.id == entry.user_id
                    )
                    result_q = await session.execute(stmt)
                    user = result_q.scalar_one_or_none()

                    if not user or not is_subscription_active(user):
                        continue

                    # Premium only
                    if user.subscription_type not in (
                        SubscriptionType.PREMIUM,
                        SubscriptionType.BUSINESS,
                    ):
                        continue

                    scan = await self.darkweb_service.scan(
                        entry.email, "email"
                    )

                    if scan.has_findings:
                        for finding in scan.findings:
                            content_hash = hashlib.sha256(
                                f"{entry.email}:{finding.source_name}"
                                f":{finding.found_date}".encode()
                            ).hexdigest()

                            already = await NotificationCRUD.was_sent(
                                session,
                                user.id,
                                "darkweb",
                                content_hash,
                            )
                            if not already:
                                await DarkWebCRUD.create_alert(
                                    session,
                                    user.id,
                                    finding.data_type,
                                    finding.source_name,
                                    finding.matched_value,
                                    finding.severity,
                                    finding.details,
                                )
                                await NotificationCRUD.log_sent(
                                    session,
                                    user.id,
                                    "darkweb",
                                    content_hash,
                                )

                    await asyncio.sleep(3)

                except Exception as e:
                    logger.error(
                        f"Dark web scan error for {entry.id}: {e}"
                    )

        logger.info("✅ Dark web scan cycle complete")

    @staticmethod
    def _mask_email(email: str) -> str:
        parts = email.split("@")
        if len(parts) == 2:
            name = parts[0]
            m = name[0] + "***" + (
                name[-1] if len(name) > 1 else ""
            )
            return f"{m}@{parts[1]}"
        return "***"