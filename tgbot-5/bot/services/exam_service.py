"""
services/exam_service.py
Генерирует временны́е слоты для зачётов.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def generate_slots(start_time: str, end_time: str, duration_minutes: int) -> list[str]:
    """
    Сгенерировать список временны́х слотов.
    Например: start=14:00, end=16:00, duration=15 → ['14:00','14:15','14:30',...]
    """
    fmt = "%H:%M"
    try:
        start = datetime.strptime(start_time.strip(), fmt)
        end   = datetime.strptime(end_time.strip(), fmt)
    except ValueError:
        return []

    slots = []
    current = start
    while current < end:
        slots.append(current.strftime(fmt))
        current += timedelta(minutes=duration_minutes)

    return slots


def validate_date(date_str: str) -> bool:
    """Проверить формат даты DD.MM.YYYY."""
    try:
        datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return True
    except ValueError:
        return False


def format_date_for_db(date_str: str) -> str:
    """Конвертировать DD.MM.YYYY → YYYY-MM-DD для SQLite."""
    dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
    return dt.strftime("%Y-%m-%d")


def format_date_for_display(date_db: str) -> str:
    """Конвертировать YYYY-MM-DD → DD.MM.YYYY для отображения."""
    try:
        dt = datetime.strptime(date_db, "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_db
