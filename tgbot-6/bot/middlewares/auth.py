"""
middlewares/auth.py
Автоматически регистрирует каждого пользователя в БД при любом обращении к боту.
Прокидывает role и has_access в data для хэндлеров.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message, CallbackQuery

from bot.database import UserRepo
from bot.config import ADMINS

log = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:

        # Извлечь пользователя из Update
        user = None
        if isinstance(event, Update):
            if event.message:
                user = event.message.from_user
            elif event.callback_query:
                user = event.callback_query.from_user

        if user:
            tid = user.id
            uname = user.username
            fname = user.full_name or ""

            # Автоматически повышаем до admin если в ADMINS
            await UserRepo.upsert(tid, uname, fname)
            if tid in ADMINS:
                await UserRepo.set_role(tid, "admin")

            row = await UserRepo.get(tid)
            data["role"]       = row["role"] if row else "user"
            data["has_access"] = bool(row["has_access"]) if row else False
            data["db_user"]    = row

        return await handler(event, data)
