"""utils/helpers.py — вспомогательные функции."""

from __future__ import annotations

import re
from datetime import datetime


def now_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_filename(name: str) -> str:
    """Убрать запрещённые символы из имени файла."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def paginate(items: list, page: int, page_size: int = 10) -> tuple[list, int]:
    """Вернуть срез и общее кол-во страниц."""
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    start = page * page_size
    end   = start + page_size
    return items[start:end], total_pages


def chunks(lst: list, n: int):
    """Разбить список на чанки по n элементов."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

