"""
services/scheduler_service.py
APScheduler: проверяет зачёты каждую минуту и отправляет уведомления
за 10 минут и в момент начала.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from bot.database import ExamSlotRepo, ExamBookingRepo, CuratorRepo

log = logging.getLogger(__name__)


async def _check_notifications(bot: Bot) -> None:
    """Вызывается каждую минуту. Ищет близкие зачёты и шлёт уведомления."""
    try:
        rows = await ExamSlotRepo.get_upcoming_unnotified()
        now = datetime.now()

        for row in rows:
            booking_id = row["booking_id"]
            student_id = row["student_id"]
            curator_id = row["curator_id"]
            meet_link  = row["meet_link"] or "—"
            slot_dt    = datetime.fromisoformat(f"{row['slot_date']} {row['slot_time']}")
            delta      = (slot_dt - now).total_seconds()

            # Уведомление за 10 минут (в диапазоне 9:00–10:59 до зачёта)
            if 540 <= delta <= 659 and not row["notified_10_min"]:
                text = (
                    f"⏳ <b>Через 10 минут зачёт!</b>\n\n"
                    f"📅 Дата: {row['slot_date']}\n"
                    f"🕐 Время: {row['slot_time']}\n"
                    f"🔗 Google Meet: {meet_link}"
                )
                await _send_safe(bot, student_id, text)
                curator = await CuratorRepo.get_by_id(curator_id)
                if curator:
                    await _send_safe(bot, curator["telegram_id"],
                        f"⏳ <b>Через 10 минут зачёт!</b>\n\n"
                        f"👨‍🎓 Ученик: {row['student_full_name']}\n"
                        f"📅 Дата: {row['slot_date']}\n"
                        f"🕐 Время: {row['slot_time']}\n"
                        f"🔗 Google Meet: {meet_link}"
                    )
                await ExamBookingRepo.set_notified(booking_id, "notified_10_min")
                log.info("Уведомление 10 мин → student=%s", student_id)

            # Уведомление в момент начала (0–59 секунд до)
            elif -60 <= delta <= 59 and not row["notified_start"]:
                text = (
                    f"⏰ <b>Время зачёта пришло!</b>\n\n"
                    f"📅 Дата: {row['slot_date']}\n"
                    f"🕐 Время: {row['slot_time']}\n"
                    f"🔗 <a href='{meet_link}'>Войти в Google Meet</a>"
                )
                await _send_safe(bot, student_id, text)
                curator = await CuratorRepo.get_by_id(curator_id)
                if curator:
                    await _send_safe(bot, curator["telegram_id"],
                        f"⏰ <b>Зачёт начался!</b>\n\n"
                        f"👨‍🎓 Ученик: {row['student_full_name']}\n"
                        f"📅 {row['slot_date']}  🕐 {row['slot_time']}\n"
                        f"🔗 <a href='{meet_link}'>Войти в Google Meet</a>"
                    )
                await ExamBookingRepo.set_notified(booking_id, "notified_start")
                log.info("Уведомление начало → student=%s", student_id)

    except Exception as e:
        log.error("Ошибка в _check_notifications: %s", e, exc_info=True)


async def _send_safe(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log.warning("Не удалось отправить уведомление → %s: %s", chat_id, e)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
    scheduler.add_job(
        _check_notifications,
        trigger=IntervalTrigger(minutes=1),
        args=[bot],
        id="exam_notifications",
        replace_existing=True,
    )
    scheduler.start()
    log.info("APScheduler запущен")
    return scheduler
