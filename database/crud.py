from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import (
    User,
    Subscription,
    CheckHistory,
    MonitoredEmail,
    SubscriptionType,
    PaymentStatus,
    CheckType,
)
import hashlib
import secrets


class UserCRUD:
    """Операции с пользователями"""

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        telegram_id: int,
        username: str | None = None,
        full_name: str = "",
        language_code: str = "ru",
        referred_by: int | None = None,
    ) -> tuple[User, bool]:
        """Получить или создать пользователя. Возвращает (user, created)"""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # Обновляем данные при каждом входе
            user.username = username
            user.full_name = full_name
            await session.commit()
            return user, False

        # Создаём нового
        referral_code = secrets.token_urlsafe(8)
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            language_code=language_code,
            referral_code=referral_code,
            referred_by=referred_by,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, True

    @staticmethod
    async def get_by_telegram_id(
        session: AsyncSession, telegram_id: int
    ) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_referral_code(
        session: AsyncSession, code: str
    ) -> User | None:
        stmt = select(User).where(User.referral_code == code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def can_check(session: AsyncSession, user: User) -> bool:
        """Проверяет, может ли пользователь делать проверку"""
        # Premium и Business — без лимитов
        if user.subscription_type != SubscriptionType.FREE:
            if user.subscription_expires and \
               user.subscription_expires > datetime.now(timezone.utc):
                return True

        # Free — 1 проверка в день
        now = datetime.now(timezone.utc)
        if user.last_check_date:
            if user.last_check_date.date() == now.date():
                from config import settings
                return user.checks_today < settings.free_checks_per_day
        return True

    @staticmethod
    async def increment_check(session: AsyncSession, user: User):
        """Увеличивает счётчик проверок"""
        now = datetime.now(timezone.utc)
        if user.last_check_date and user.last_check_date.date() == now.date():
            user.checks_today += 1
        else:
            user.checks_today = 1
            user.last_check_date = now
        user.total_checks += 1
        await session.commit()

    @staticmethod
    async def activate_subscription(
        session: AsyncSession,
        user: User,
        sub_type: SubscriptionType,
        months: int = 1,
    ):
        """Активирует подписку"""
        now = datetime.now(timezone.utc)
        user.subscription_type = sub_type
        user.subscription_expires = now + timedelta(days=30 * months)
        await session.commit()

    @staticmethod
    async def get_stats(session: AsyncSession) -> dict:
        """Статистика для админки"""
        total = await session.scalar(select(func.count(User.id)))
        premium = await session.scalar(
            select(func.count(User.id)).where(
                User.subscription_type == SubscriptionType.PREMIUM
            )
        )
        business = await session.scalar(
            select(func.count(User.id)).where(
                User.subscription_type == SubscriptionType.BUSINESS
            )
        )
        today = datetime.now(timezone.utc).date()
        new_today = await session.scalar(
            select(func.count(User.id)).where(
                func.date(User.created_at) == today
            )
        )
        return {
            "total": total or 0,
            "premium": premium or 0,
            "business": business or 0,
            "new_today": new_today or 0,
        }


class SubscriptionCRUD:
    """Операции с подписками/платежами"""

    @staticmethod
    async def create_payment(
        session: AsyncSession,
        user_id: int,
        payment_id: str,
        sub_type: SubscriptionType,
        amount: int,
    ) -> Subscription:
        sub = Subscription(
            user_id=user_id,
            payment_id=payment_id,
            subscription_type=sub_type,
            amount=amount,
            status=PaymentStatus.PENDING,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub

    @staticmethod
    async def confirm_payment(
        session: AsyncSession, payment_id: str
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.payment_id == payment_id
        )
        result = await session.execute(stmt)
        sub = result.scalar_one_or_none()

        if not sub:
            return None

        now = datetime.now(timezone.utc)
        sub.status = PaymentStatus.SUCCEEDED
        sub.period_start = now
        sub.period_end = now + timedelta(days=30)
        await session.commit()
        return sub

    @staticmethod
    async def get_by_payment_id(
        session: AsyncSession, payment_id: str
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.payment_id == payment_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


class CheckHistoryCRUD:
    """Операции с историей проверок"""

    @staticmethod
    async def add(
        session: AsyncSession,
        user_id: int,
        check_type: CheckType,
        query_value: str,
        breaches_found: int = 0,
        result_data: dict | None = None,
    ) -> CheckHistory:
        query_hash = hashlib.sha256(
            query_value.lower().encode()
        ).hexdigest()

        # Маскируем значение для хранения
        masked = CheckHistoryCRUD._mask_value(query_value, check_type)

        entry = CheckHistory(
            user_id=user_id,
            check_type=check_type,
            query_value=masked,
            query_hash=query_hash,
            breaches_found=breaches_found,
            result_data=result_data,
        )
        session.add(entry)
        await session.commit()
        return entry

    @staticmethod
    def _mask_value(value: str, check_type: CheckType) -> str:
        """Маскирует данные для безопасного хранения"""
        if check_type == CheckType.EMAIL:
            parts = value.split("@")
            if len(parts) == 2:
                name = parts[0]
                masked_name = name[0] + "***" + (name[-1] if len(name) > 1 else "")
                return f"{masked_name}@{parts[1]}"
        elif check_type == CheckType.PHONE:
            if len(value) > 4:
                return value[:3] + "****" + value[-2:]
        elif check_type == CheckType.PASSWORD:
            return "********"
        return value[:2] + "***"

    @staticmethod
    async def get_user_history(
        session: AsyncSession, user_id: int, limit: int = 20
    ) -> list[CheckHistory]:
        stmt = (
            select(CheckHistory)
            .where(CheckHistory.user_id == user_id)
            .order_by(CheckHistory.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

# ─── Добавить в database/crud.py ─────────────────────────

from database.models import (
    MonitoredEmail,
    FamilyMember,
    DarkWebAlert,
    NotificationLog,
)


class MonitorCRUD:
    """Операции с мониторингом"""

    @staticmethod
    async def add_email(
        session: AsyncSession,
        user_id: int,
        email: str,
    ) -> MonitoredEmail | None:
        """Добавить email на мониторинг"""
        # Проверяем дубликат
        stmt = select(MonitoredEmail).where(
            MonitoredEmail.user_id == user_id,
            MonitoredEmail.email == email.lower(),
            MonitoredEmail.is_active == True,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return None  # Уже мониторится

        entry = MonitoredEmail(
            user_id=user_id,
            email=email.lower(),
            is_active=True,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry

    @staticmethod
    async def remove_email(
        session: AsyncSession,
        user_id: int,
        email_id: int,
    ) -> bool:
        """Убрать email с мониторинга"""
        stmt = select(MonitoredEmail).where(
            MonitoredEmail.id == email_id,
            MonitoredEmail.user_id == user_id,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        entry.is_active = False
        await session.commit()
        return True

    @staticmethod
    async def get_user_monitored(
        session: AsyncSession,
        user_id: int,
    ) -> list[MonitoredEmail]:
        """Получить все мониторимые email пользователя"""
        stmt = (
            select(MonitoredEmail)
            .where(
                MonitoredEmail.user_id == user_id,
                MonitoredEmail.is_active == True,
            )
            .order_by(MonitoredEmail.created_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_all_active(
        session: AsyncSession,
    ) -> list[MonitoredEmail]:
        """Все активные мониторинги (для фоновой задачи)"""
        stmt = (
            select(MonitoredEmail)
            .where(MonitoredEmail.is_active == True)
            .order_by(MonitoredEmail.last_checked.asc().nullsfirst())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_user_monitored(
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """Количество мониторимых email"""
        stmt = select(func.count(MonitoredEmail.id)).where(
            MonitoredEmail.user_id == user_id,
            MonitoredEmail.is_active == True,
        )
        result = await session.scalar(stmt)
        return result or 0

    @staticmethod
    async def update_check_result(
        session: AsyncSession,
        monitor_id: int,
        breach_count: int,
    ):
        """Обновить результат последней проверки"""
        stmt = select(MonitoredEmail).where(
            MonitoredEmail.id == monitor_id
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry:
            entry.last_checked = datetime.now(timezone.utc)
            entry.last_breach_count = breach_count
            await session.commit()


class FamilyCRUD:
    """Операции с семейными аккаунтами"""

    MAX_FAMILY_MEMBERS = 3  # Premium
    MAX_FAMILY_BUSINESS = 10  # Business

    @staticmethod
    async def add_member(
        session: AsyncSession,
        owner_id: int,
        name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> FamilyMember | None:
        """Добавить члена семьи"""
        member = FamilyMember(
            owner_id=owner_id,
            name=name,
            email=email,
            phone=phone,
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)
        return member

    @staticmethod
    async def get_members(
        session: AsyncSession,
        owner_id: int,
    ) -> list[FamilyMember]:
        """Получить членов семьи"""
        stmt = (
            select(FamilyMember)
            .where(
                FamilyMember.owner_id == owner_id,
                FamilyMember.is_active == True,
            )
            .order_by(FamilyMember.created_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_members(
        session: AsyncSession,
        owner_id: int,
    ) -> int:
        """Количество членов семьи"""
        stmt = select(func.count(FamilyMember.id)).where(
            FamilyMember.owner_id == owner_id,
            FamilyMember.is_active == True,
        )
        result = await session.scalar(stmt)
        return result or 0

    @staticmethod
    async def remove_member(
        session: AsyncSession,
        owner_id: int,
        member_id: int,
    ) -> bool:
        """Удалить члена семьи"""
        stmt = select(FamilyMember).where(
            FamilyMember.id == member_id,
            FamilyMember.owner_id == owner_id,
        )
        result = await session.execute(stmt)
        member = result.scalar_one_or_none()
        if not member:
            return False
        member.is_active = False
        await session.commit()
        return True


class DarkWebCRUD:
    """Операции с dark web алертами"""

    @staticmethod
    async def create_alert(
        session: AsyncSession,
        user_id: int,
        alert_type: str,
        source: str,
        matched_data: str,
        severity: str = "medium",
        details: dict | None = None,
    ) -> DarkWebAlert:
        alert = DarkWebAlert(
            user_id=user_id,
            alert_type=alert_type,
            source=source,
            matched_data=matched_data,
            severity=severity,
            details=details,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert

    @staticmethod
    async def get_user_alerts(
        session: AsyncSession,
        user_id: int,
        unread_only: bool = False,
        limit: int = 20,
    ) -> list[DarkWebAlert]:
        stmt = select(DarkWebAlert).where(
            DarkWebAlert.user_id == user_id
        )
        if unread_only:
            stmt = stmt.where(DarkWebAlert.is_read == False)
        stmt = stmt.order_by(
            DarkWebAlert.created_at.desc()
        ).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def mark_read(
        session: AsyncSession,
        user_id: int,
        alert_id: int | None = None,
    ):
        """Пометить алерты прочитанными"""
        if alert_id:
            stmt = select(DarkWebAlert).where(
                DarkWebAlert.id == alert_id,
                DarkWebAlert.user_id == user_id,
            )
            result = await session.execute(stmt)
            alert = result.scalar_one_or_none()
            if alert:
                alert.is_read = True
        else:
            # Все
            stmt = (
                update(DarkWebAlert)
                .where(
                    DarkWebAlert.user_id == user_id,
                    DarkWebAlert.is_read == False,
                )
                .values(is_read=True)
            )
            await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def count_unread(
        session: AsyncSession,
        user_id: int,
    ) -> int:
        stmt = select(func.count(DarkWebAlert.id)).where(
            DarkWebAlert.user_id == user_id,
            DarkWebAlert.is_read == False,
        )
        result = await session.scalar(stmt)
        return result or 0


class NotificationCRUD:
    """Проверка: не отправляли ли мы уже такое уведомление"""

    @staticmethod
    async def was_sent(
        session: AsyncSession,
        user_id: int,
        notification_type: str,
        content_hash: str,
    ) -> bool:
        stmt = select(func.count(NotificationLog.id)).where(
            NotificationLog.user_id == user_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.content_hash == content_hash,
        )
        result = await session.scalar(stmt)
        return (result or 0) > 0

    @staticmethod
    async def log_sent(
        session: AsyncSession,
        user_id: int,
        notification_type: str,
        content_hash: str,
    ):
        entry = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            content_hash=content_hash,
        )
        session.add(entry)
        await session.commit()

from database.models import BusinessDomain


class BusinessCRUD:
    """Операции с бизнес-доменами"""

    @staticmethod
    async def add_domain(
        session: AsyncSession,
        user_id: int,
        domain: str,
        company_name: str = "",
    ) -> BusinessDomain | None:
        """Добавить корпоративный домен"""
        stmt = select(BusinessDomain).where(
            BusinessDomain.user_id == user_id,
            BusinessDomain.domain == domain.lower(),
            BusinessDomain.is_active == True,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return None

        entry = BusinessDomain(
            user_id=user_id,
            domain=domain.lower(),
            company_name=company_name,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry

    @staticmethod
    async def get_domains(
        session: AsyncSession,
        user_id: int,
    ) -> list[BusinessDomain]:
        stmt = (
            select(BusinessDomain)
            .where(
                BusinessDomain.user_id == user_id,
                BusinessDomain.is_active == True,
            )
            .order_by(BusinessDomain.created_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def remove_domain(
        session: AsyncSession,
        user_id: int,
        domain_id: int,
    ) -> bool:
        stmt = select(BusinessDomain).where(
            BusinessDomain.id == domain_id,
            BusinessDomain.user_id == user_id,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        entry.is_active = False
        await session.commit()
        return True

    @staticmethod
    async def update_scan_results(
        session: AsyncSession,
        domain_id: int,
        emails_found: int,
        breaches_found: int,
        results: dict,
    ):
        stmt = select(BusinessDomain).where(
            BusinessDomain.id == domain_id
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry:
            entry.total_emails_found = emails_found
            entry.total_breaches_found = breaches_found
            entry.scan_results = results
            entry.last_scan = datetime.now(timezone.utc)
            await session.commit()


class AdminCRUD:
    """Операции для админ-панели"""

    @staticmethod
    async def get_all_users(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
        subscription_filter: SubscriptionType | None = None,
    ) -> list[User]:
        stmt = select(User).order_by(User.created_at.desc())
        if subscription_filter:
            stmt = stmt.where(
                User.subscription_type == subscription_filter
            )
        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_users(
        session: AsyncSession,
        subscription_filter: SubscriptionType | None = None,
    ) -> int:
        stmt = select(func.count(User.id))
        if subscription_filter:
            stmt = stmt.where(
                User.subscription_type == subscription_filter
            )
        result = await session.scalar(stmt)
        return result or 0

    @staticmethod
    async def block_user(
        session: AsyncSession,
        telegram_id: int,
    ) -> bool:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.is_blocked = True
            await session.commit()
            return True
        return False

    @staticmethod
    async def unblock_user(
        session: AsyncSession,
        telegram_id: int,
    ) -> bool:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.is_blocked = False
            await session.commit()
            return True
        return False

    @staticmethod
    async def grant_subscription(
        session: AsyncSession,
        telegram_id: int,
        sub_type: SubscriptionType,
        days: int = 30,
    ) -> bool:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.subscription_type = sub_type
            user.subscription_expires = (
                datetime.now(timezone.utc) + timedelta(days=days)
            )
            await session.commit()
            return True
        return False

    @staticmethod
    async def get_revenue_stats(
        session: AsyncSession,
    ) -> dict:
        """Статистика по доходам"""
        from database.models import Subscription, PaymentStatus

        # Всего успешных платежей
        stmt = select(
            func.sum(Subscription.amount),
            func.count(Subscription.id),
        ).where(Subscription.status == PaymentStatus.SUCCEEDED)
        result = await session.execute(stmt)
        row = result.one_or_none()

        total_revenue = (row[0] or 0) // 100 if row else 0
        total_payments = row[1] or 0 if row else 0

        # За последний месяц
        month_ago = datetime.now(timezone.utc) - timedelta(days=30)
        stmt_month = select(
            func.sum(Subscription.amount),
            func.count(Subscription.id),
        ).where(
            Subscription.status == PaymentStatus.SUCCEEDED,
            Subscription.created_at >= month_ago,
        )
        result_month = await session.execute(stmt_month)
        row_m = result_month.one_or_none()

        month_revenue = (row_m[0] or 0) // 100 if row_m else 0
        month_payments = row_m[1] or 0 if row_m else 0

        # За сегодня
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stmt_today = select(
            func.sum(Subscription.amount),
            func.count(Subscription.id),
        ).where(
            Subscription.status == PaymentStatus.SUCCEEDED,
            Subscription.created_at >= today_start,
        )
        result_today = await session.execute(stmt_today)
        row_t = result_today.one_or_none()

        today_revenue = (row_t[0] or 0) // 100 if row_t else 0
        today_payments = row_t[1] or 0 if row_t else 0

        return {
            "total_revenue": total_revenue,
            "total_payments": total_payments,
            "month_revenue": month_revenue,
            "month_payments": month_payments,
            "today_revenue": today_revenue,
            "today_payments": today_payments,
        }

    @staticmethod
    async def get_check_stats(
        session: AsyncSession,
    ) -> dict:
        """Статистика проверок"""
        from database.models import CheckHistory

        total = await session.scalar(
            select(func.count(CheckHistory.id))
        )

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today = await session.scalar(
            select(func.count(CheckHistory.id)).where(
                CheckHistory.created_at >= today_start
            )
        )

        with_breaches = await session.scalar(
            select(func.count(CheckHistory.id)).where(
                CheckHistory.breaches_found > 0
            )
        )

        return {
            "total_checks": total or 0,
            "today_checks": today or 0,
            "checks_with_breaches": with_breaches or 0,
        }                