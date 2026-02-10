import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)

from config import settings
from database.engine import create_db, async_session
from bot.handlers import get_all_routers
from bot.middlewares.throttling import (
    ThrottlingMiddleware,
    DatabaseMiddleware,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Block check middleware ──────────────────────────────

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery


class BlockCheckMiddleware(BaseMiddleware):
    """Проверяет, не заблокирован ли пользователь"""

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        session = data.get("session")
        if session and event.from_user:
            from database.crud import UserCRUD

            user = await UserCRUD.get_by_telegram_id(
                session, event.from_user.id
            )
            if user and user.is_blocked:
                if isinstance(event, Message):
                    await event.answer(
                        "🚫 Ваш аккаунт заблокирован. "
                        "Обратитесь в поддержку."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "🚫 Аккаунт заблокирован",
                        show_alert=True,
                    )
                return
        return await handler(event, data)


# ─── YooKassa Webhook ────────────────────────────────────

async def yookassa_webhook_handler(
    request: web.Request,
) -> web.Response:
    try:
        data = await request.json()
        logger.info(
            f"YooKassa webhook: {data.get('event', 'unknown')}"
        )

        event = data.get("event")
        payment_object = data.get("object", {})
        payment_id = payment_object.get("id")

        if event == "payment.succeeded" and payment_id:
            from database.crud import UserCRUD, SubscriptionCRUD
            from database.models import User
            from sqlalchemy import select

            async with async_session() as session:
                sub = await SubscriptionCRUD.confirm_payment(
                    session, payment_id
                )
                if sub:
                    stmt = select(User).where(
                        User.id == sub.user_id
                    )
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()

                    if user:
                        await UserCRUD.activate_subscription(
                            session, user, sub.subscription_type
                        )

                        bot = request.app.get("bot")
                        if bot:
                            from bot.utils.helpers import (
                                PAYMENT_SUCCESS_TEXT,
                                format_subscription_name,
                                format_date,
                            )

                            try:
                                await bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=PAYMENT_SUCCESS_TEXT.format(
                                        plan=format_subscription_name(
                                            sub.subscription_type
                                        ),
                                        amount=sub.amount // 100,
                                        expires=format_date(
                                            user.subscription_expires
                                        ),
                                    ),
                                    parse_mode="HTML",
                                )
                            except Exception as e:
                                logger.error(
                                    f"Notify error: {e}"
                                )

                        logger.info(
                            f"Sub activated: {user.telegram_id}"
                        )

        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"YooKassa webhook error: {e}")
        return web.Response(status=200, text="OK")


# ─── Health check для Railway ────────────────────────────

async def health_handler(request: web.Request) -> web.Response:
    return web.Response(status=200, text="OK")


# ─── Setup ───────────────────────────────────────────────

async def on_startup(bot: Bot):
    await create_db()
    logger.info("✅ Database initialized")

    from monitoring.scheduler import setup_scheduler
    setup_scheduler(bot=bot)
    logger.info("✅ Monitoring scheduler started")

    if settings.webhook_host:
        await bot.set_webhook(
            url=settings.bot_webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
        )
        info = await bot.get_webhook_info()
        logger.info(f"✅ Webhook set: {info.url}")
        if info.last_error_message:
            logger.error(f"⚠️ Webhook error: {info.last_error_message}")


async def on_shutdown(bot: Bot):
    from monitoring.scheduler import stop_scheduler
    stop_scheduler()
    # НЕ удаляем webhook при shutdown — Railway перезапускает часто
    logger.info("🔴 Bot stopped (webhook kept)")

def create_bot_and_dp() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
    )

    dp = Dispatcher()

    # Middlewares — порядок важен!
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(
        ThrottlingMiddleware(rate_limit=0.3)
    )
    dp.message.middleware(DatabaseMiddleware(async_session))
    dp.callback_query.middleware(
        DatabaseMiddleware(async_session)
    )
    dp.message.middleware(BlockCheckMiddleware())
    dp.callback_query.middleware(BlockCheckMiddleware())

    # Routers
    for router in get_all_routers():
        dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return bot, dp


async def run_polling():
    bot, dp = create_bot_and_dp()
    logger.info("🚀 Starting POLLING mode...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


def run_webhook():
    bot, dp = create_bot_and_dp()

    app = web.Application()
    app["bot"] = bot

    # Routes
    app.router.add_get("/health", health_handler)
    app.router.add_post(
        settings.webhook_path, yookassa_webhook_handler
    )

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp, bot=bot
    )
    webhook_handler.register(
        app, path=settings.bot_webhook_path
    )
    setup_application(app, dp, bot=bot)

    logger.info("🚀 Starting WEBHOOK mode...")
    logger.info(f"   Bot: {settings.bot_webhook_path}")
    logger.info(f"   YooKassa: {settings.webhook_path}")
    logger.info(f"   Health: /health")

    port = int(__import__("os").environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    if settings.webhook_host:
        run_webhook()
    else:

        asyncio.run(run_polling())
