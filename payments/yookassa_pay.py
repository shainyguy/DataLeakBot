import uuid
from datetime import datetime, timezone, timedelta
from yookassa import Configuration, Payment
from config import settings
from database.models import SubscriptionType

# Инициализация YooKassa
Configuration.account_id = settings.yookassa_shop_id
Configuration.secret_key = settings.yookassa_secret_key


PLAN_DETAILS = {
    SubscriptionType.PREMIUM: {
        "amount": settings.premium_price,
        "description": "DataLeakBot Premium — 1 месяц",
        "title": "⭐ Premium",
    },
    SubscriptionType.BUSINESS: {
        "amount": settings.business_price,
        "description": "DataLeakBot Business — 1 месяц",
        "title": "🏢 Business",
    },
}


class YooKassaService:
    """Сервис для работы с YooKassa"""

    @staticmethod
    def create_payment(
        sub_type: SubscriptionType,
        telegram_id: int,
    ) -> dict:
        """
        Создаёт платёж в YooKassa.
        Возвращает {"payment_id": ..., "payment_url": ..., "amount": ...}
        """
        plan = PLAN_DETAILS.get(sub_type)
        if not plan:
            raise ValueError(f"Unknown subscription type: {sub_type}")

        idempotence_key = str(uuid.uuid4())

        payment = Payment.create(
            {
                "amount": {
                    "value": f"{plan['amount']}.00",
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": settings.yookassa_return_url,
                },
                "capture": True,
                "description": plan["description"],
                "metadata": {
                    "telegram_id": str(telegram_id),
                    "subscription_type": sub_type.value,
                },
            },
            idempotency_key=idempotence_key,
        )

        return {
            "payment_id": payment.id,
            "payment_url": payment.confirmation.confirmation_url,
            "amount": plan["amount"],
        }

    @staticmethod
    def check_payment(payment_id: str) -> dict:
        """
        Проверяет статус платежа.
        Возвращает {"status": ..., "paid": ..., "metadata": ...}
        """
        payment = Payment.find_one(payment_id)
        return {
            "status": payment.status,
            "paid": payment.paid,
            "metadata": payment.metadata or {},
            "amount": payment.amount.value if payment.amount else "0",
        }

    @staticmethod
    def get_plan_info(sub_type: SubscriptionType) -> dict | None:
        return PLAN_DETAILS.get(sub_type)