"""
main.py — точка входа Telegram-бота.
Регистрирует все роутеры, middleware, запускает APScheduler и polling.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.config import BOT_TOKEN, ADMINS, LOGS_DIR
from bot.database import init_db
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.logging_mw import LoggingMiddleware
from bot.services.scheduler_service import setup_scheduler

from bot.handlers import (
    user, workbooks, checklists,
    submissions, practice, exams, curator, admin
)


# ─────────────────────────────────────────────────────────────────────────────
def setup_logging() -> None:
    log_file = LOGS_DIR / "bot.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ]
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)
    log.info("Запуск бота...")

    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # ── Middleware ────────────────────────────────────────────────────────────
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(AuthMiddleware())

    # ── Глобальный обработчик ошибок ─────────────────────────────────────────
    @dp.error()
    async def global_error_handler(event: ErrorEvent) -> None:
        log.error(
            "Необработанная ошибка: %s",
            event.exception,
            exc_info=event.exception
        )
        # Попробовать уведомить пользователя
        try:
            upd = event.update
            chat_id = None
            if upd.message:
                chat_id = upd.message.chat.id
            elif upd.callback_query:
                chat_id = upd.callback_query.message.chat.id
                await upd.callback_query.answer("⚠️ Произошла ошибка. Попробуйте ещё раз.")
            if chat_id:
                await bot.send_message(
                    chat_id,
                    "⚠️ Произошла внутренняя ошибка. Попробуйте ещё раз или напишите /start"
                )
        except Exception:
            pass

        # Уведомить первого админа
        if ADMINS:
            try:
                err_text = str(event.exception)[:500]
                await bot.send_message(
                    ADMINS[0],
                    f"🚨 <b>Ошибка в боте:</b>\n<code>{err_text}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # ── Роутеры (порядок важен: более специфичные — первыми) ─────────────────
    dp.include_router(admin.router)        # Только для admin
    dp.include_router(curator.router)      # Только для curator+
    dp.include_router(user.router)         # /start, /help, /myid, профиль
    dp.include_router(workbooks.router)    # Рабочие тетради
    dp.include_router(checklists.router)   # Чек-листы
    dp.include_router(submissions.router)  # Сдача РТ
    dp.include_router(practice.router)    # Скрин практики
    dp.include_router(exams.router)        # Запись на зачёт

    # ── APScheduler ──────────────────────────────────────────────────────────
    scheduler = setup_scheduler(bot)

    # ── Показать информацию о боте при старте ────────────────────────────────
    me = await bot.get_me()
    log.info("Бот запущен: @%s (id=%s)", me.username, me.id)
    log.info("Администраторы: %s", ADMINS)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True   # Игнорировать накопившиеся сообщения при рестарте
        )
    finally:
        scheduler.shutdown()
        await bot.session.close()
        log.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
