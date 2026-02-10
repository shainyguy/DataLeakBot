from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    admin_ids: List[int] = []

    # Database
    database_url: str = "sqlite+aiosqlite:///dataleakbot.db"

    # YooKassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = ""

    # GigaChat
    gigachat_api_key: str = ""

    # HIBP
    hibp_api_key: str = ""

    # Webhook
    webhook_host: str = ""
    webhook_path: str = "/yookassa/webhook"
    bot_webhook_path: str = "/bot/webhook"

    # Subscription prices (в рублях)
    premium_price: int = 790
    business_price: int = 1790

    # Free tier limits
    free_checks_per_day: int = 1

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_host}{self.webhook_path}"

    @property
    def bot_webhook_url(self) -> str:
        return f"{self.webhook_host}{self.bot_webhook_path}"


settings = Settings()