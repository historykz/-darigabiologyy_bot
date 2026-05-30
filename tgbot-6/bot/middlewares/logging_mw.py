"""
middlewares/logging_mw.py
Логирует все входящие сообщения и callback-и.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

log = logging.getLogger("updates")


class LoggingMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            if event.message:
                m = event.message
                log.debug("MSG uid=%s text=%r", m.from_user.id if m.from_user else "?", m.text)
            elif event.callback_query:
                c = event.callback_query
                log.debug("CBQ uid=%s data=%r", c.from_user.id, c.data)
        return await handler(event, data)
