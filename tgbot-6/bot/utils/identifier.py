"""
utils/identifier.py

Парсит строку с ID/username-ами пользователей.
Поддерживает:
  — @username
  — числовой Telegram ID
  — смешанный список через запятую, пробел, новую строку

Пример входа:
  @ivanov, 123456789
  @petrov
  987654321 @sidorov

Пример выхода:
  ['@ivanov', '123456789', '@petrov', '987654321', '@sidorov']
"""

from __future__ import annotations
import re


def parse_identifiers(text: str) -> list[str]:
    """
    Разбить текст на список идентификаторов.
    Каждый элемент — либо '@username', либо числовой ID-строка.
    Максимум 15 штук.
    """
    # Нормализуем разделители
    text = text.replace(",", " ").replace(";", " ")
    tokens = text.split()

    result = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        # @username
        if t.startswith("@") and len(t) >= 2:
            username = t[1:]
            if re.match(r"^[A-Za-z0-9_]{3,32}$", username):
                result.append(t.lower())
        # Числовой ID
        elif t.lstrip("-").isdigit():
            result.append(t)
        # username без @ (если выглядит как username)
        elif re.match(r"^[A-Za-z][A-Za-z0-9_]{2,31}$", t):
            result.append(f"@{t.lower()}")

    # Убрать дубликаты, сохранив порядок
    seen = set()
    unique = []
    for r in result:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return unique[:15]  # Лимит 15 человек


def format_identifier_list(identifiers: list[str]) -> str:
    """Красиво отформатировать список идентификаторов для отображения."""
    return "\n".join(f"  • {i}" for i in identifiers)
