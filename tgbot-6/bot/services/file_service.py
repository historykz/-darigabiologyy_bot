"""
services/file_service.py
Скачивает файлы из Telegram и сохраняет на диск.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiofiles
from aiogram import Bot
from aiogram.types import Document, PhotoSize, Message

log = logging.getLogger(__name__)


async def save_telegram_file(bot: Bot, file_id: str, dest_dir: str,
                              filename: str) -> str:
    """
    Скачать файл из Telegram по file_id и сохранить в dest_dir/filename.
    Возвращает полный путь к сохранённому файлу.
    """
    dest = Path(dest_dir) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    file = await bot.get_file(file_id)
    file_bytes = await bot.download_file(file.file_path)

    async with aiofiles.open(dest, "wb") as f:
        await f.write(file_bytes.read())

    log.info("Файл сохранён: %s", dest)
    return str(dest)


def get_file_extension(message: Message) -> tuple[str, str]:
    """
    Определить тип и расширение файла из сообщения.
    Возвращает (file_id, extension).
    """
    if message.document:
        doc: Document = message.document
        name = doc.file_name or "file"
        ext  = Path(name).suffix.lower() or ".bin"
        return doc.file_id, ext

    if message.photo:
        photo: PhotoSize = message.photo[-1]  # самое большое фото
        return photo.file_id, ".jpg"

    if message.video:
        return message.video.file_id, ".mp4"

    if message.audio:
        return message.audio.file_id, ".mp3"

    if message.voice:
        return message.voice.file_id, ".ogg"

    return "", ""


def get_file_type(ext: str) -> str:
    """Определить тип файла по расширению для UI."""
    ext = ext.lower()
    mapping = {
        ".pdf": "PDF",
        ".docx": "Word",
        ".doc": "Word",
        ".xlsx": "Excel",
        ".xls": "Excel",
        ".pptx": "PowerPoint",
        ".jpg": "Фото",
        ".jpeg": "Фото",
        ".png": "Фото",
        ".mp4": "Видео",
        ".mp3": "Аудио",
    }
    return mapping.get(ext, "Файл")
