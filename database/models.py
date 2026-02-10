from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    JSON,
    Enum as SAEnum,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


# ─── Enums ───────────────────────────────────────────────

class SubscriptionType(str, enum.Enum):
    FREE = "free"
    PREMIUM = "premium"
    BUSINESS = "business"


class CheckType(str, enum.Enum):
    EMAIL = "email"
    PHONE = "phone"
    PASSWORD = "password"
    USERNAME = "username"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    REFUNDED = "refunded"


# ─── User ────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    language_code: Mapped[str] = mapped_column(String(10), default="ru")

    # Subscription
    subscription_type: Mapped[SubscriptionType] = mapped_column(
        SAEnum(SubscriptionType), default=SubscriptionType.FREE
    )
    subscription_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Limits
    checks_today: Mapped[int] = mapped_column(Integer, default=0)
    last_check_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_checks: Mapped[int] = mapped_column(Integer, default=0)

    # Referral
    referral_code: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )
    referred_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    referral_earnings: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    check_history: Mapped[list["CheckHistory"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    monitored_emails: Mapped[list["MonitoredEmail"]] = relationship(
        back_populates="user", lazy="selectin"
    )

    def __repr__(self):
        return f"<User {self.telegram_id} ({self.subscription_type.value})>"


# ─── Subscription / Payments ─────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # YooKassa
    payment_id: Mapped[str] = mapped_column(String(100), unique=True)
    subscription_type: Mapped[SubscriptionType] = mapped_column(
        SAEnum(SubscriptionType)
    )
    amount: Mapped[int] = mapped_column(Integer)  # в копейках
    currency: Mapped[str] = mapped_column(String(3), default="RUB")

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), default=PaymentStatus.PENDING
    )

    # Period
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        Index("idx_sub_user_status", "user_id", "status"),
    )


# ─── Check History ───────────────────────────────────────

class CheckHistory(Base):
    __tablename__ = "check_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    check_type: Mapped[CheckType] = mapped_column(SAEnum(CheckType))
    query_value: Mapped[str] = mapped_column(String(500))  # хешированный
    query_hash: Mapped[str] = mapped_column(String(64), index=True)

    # Results
    breaches_found: Mapped[int] = mapped_column(Integer, default=0)
    result_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="check_history")

    __table_args__ = (
        Index("idx_check_user_date", "user_id", "created_at"),
    )


# ─── Monitored Emails ───────────────────────────────────

class MonitoredEmail(Base):
    __tablename__ = "monitored_emails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    email: Mapped[str] = mapped_column(String(320))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_checked: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_breach_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="monitored_emails")

    __table_args__ = (
        Index("idx_monitored_user", "user_id", "is_active"),
    )


# ─── Добавить в database/models.py после MonitoredEmail ──


class FamilyMember(Base):
    """Семейный аккаунт (Premium)"""
    __tablename__ = "family_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_checked: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    breaches_found: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_family_owner", "owner_id", "is_active"),
    )


class DarkWebAlert(Base):
    """Алерты из dark web мониторинга"""
    __tablename__ = "darkweb_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    alert_type: Mapped[str] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(200), default="")
    matched_data: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_darkweb_user", "user_id", "is_read"),
    )


class NotificationLog(Base):
    """Лог уведомлений (чтобы не спамить)"""
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    notification_type: Mapped[str] = mapped_column(String(50))
    content_hash: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_notif_user_type", "user_id", "notification_type"),
    )  


class BusinessDomain(Base):
    """Корпоративный домен для бизнес-мониторинга"""
    __tablename__ = "business_domains"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    domain: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str] = mapped_column(String(255), default="")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Статистика
    total_emails_found: Mapped[int] = mapped_column(Integer, default=0)
    total_breaches_found: Mapped[int] = mapped_column(Integer, default=0)
    last_scan: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scan_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_biz_domain_user", "user_id", "is_active"),
    )      