"""
APScheduler — фоновые задачи мониторинга.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from bot.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
monitoring_service: MonitoringService | None = None


def setup_scheduler(bot=None):
    """Настройка и запуск планировщика"""
    global monitoring_service
    monitoring_service = MonitoringService(bot=bot)

    # Проверка утечек каждые 6 часов
    scheduler.add_job(
        monitoring_service.run_monitoring_cycle,
        trigger=IntervalTrigger(hours=6),
        id="leak_monitoring",
        name="Leak Monitoring Cycle",
        replace_existing=True,
        max_instances=1,
    )

    # Dark web сканирование раз в день (в 3:00 MSK = 0:00 UTC)
    scheduler.add_job(
        monitoring_service.run_darkweb_cycle,
        trigger=CronTrigger(hour=0, minute=0),
        id="darkweb_monitoring",
        name="Dark Web Monitoring",
        replace_existing=True,
        max_instances=1,
    )

    # Проверка истёкших подписок каждые 2 часа
    scheduler.add_job(
        _check_expired_subscriptions,
        trigger=IntervalTrigger(hours=2),
        id="subscription_check",
        name="Subscription Expiry Check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("📅 Scheduler started with jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"   - {job.name} ({job.trigger})")


async def _check_expired_subscriptions():
    """Уведомление об истекающих подписках"""
    from database.engine import async_session
    from database.models import User, SubscriptionType
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select

    async with async_session() as session:
        # За 3 дня до истечения
        warn_date = datetime.now(timezone.utc) + timedelta(days=3)

        stmt = select(User).where(
            User.subscription_type != SubscriptionType.FREE,
            User.subscription_expires != None,
            User.subscription_expires <= warn_date,
            User.subscription_expires > datetime.now(timezone.utc),
        )
        result = await session.execute(stmt)
        users = result.scalars().all()

        if monitoring_service and monitoring_service.bot:
            for user in users:
                try:
                    days_left = (
                        user.subscription_expires
                        - datetime.now(timezone.utc)
                    ).days

                    await monitoring_service.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f"⏰ <b>Подписка истекает!</b>\n\n"
                            f"Ваша подписка истечёт через "
                            f"<b>{days_left}</b> дн.\n"
                            f"Продлите для сохранения "
                            f"мониторинга.\n\n"
                            f"/subscribe — продлить"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass


def stop_scheduler():
    """Остановка планировщика"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("📅 Scheduler stopped")