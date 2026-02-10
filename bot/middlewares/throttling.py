from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
import time


class ThrottlingMiddleware(BaseMiddleware):
    """Антиспам мидлварь"""

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self.user_last_request: Dict[int, float] = {}
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        current_time = time.monotonic()

        last_time = self.user_last_request.get(user_id, 0)
        if current_time - last_time < self.rate_limit:
            # Пользователь слишком быстро шлёт запросы
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Подождите немного...", show_alert=False)
            return

        self.user_last_request[user_id] = current_time
        return await handler(event, data)


class DatabaseMiddleware(BaseMiddleware):
    """Мидлварь для передачи сессии БД"""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)