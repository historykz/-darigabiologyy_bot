"""
services/pdf_service.py
Собирает список фото → нормализует через Pillow → упаковывает в PDF через img2pdf.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiofiles
import img2pdf
from PIL import Image

log = logging.getLogger(__name__)


async def photos_to_pdf(photo_paths: list[str], output_path: str) -> str:
    """
    Конвертировать список фото в один PDF.
    Возвращает путь к готовому PDF.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _sync_photos_to_pdf, photo_paths, output_path)
    return result


def _sync_photos_to_pdf(photo_paths: list[str], output_path: str) -> str:
    """Синхронная функция — запускается в executor."""
    jpeg_paths: list[str] = []

    for idx, p in enumerate(photo_paths):
        try:
            img = Image.open(p)
            # Конвертировать в RGB (убрать alpha-канал если есть)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            # Сохранить как JPEG (img2pdf лучше работает с JPEG)
            jpeg_path = str(Path(p).with_suffix(f".conv{idx}.jpg"))
            img.save(jpeg_path, "JPEG", quality=90)
            jpeg_paths.append(jpeg_path)
        except Exception as e:
            log.error("Ошибка обработки фото %s: %s", p, e)

    if not jpeg_paths:
        raise ValueError("Нет фото для создания PDF")

    pdf_bytes = img2pdf.convert(jpeg_paths)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)

    # Удалить временные конвертированные файлы
    for jp in jpeg_paths:
        try:
            Path(jp).unlink(missing_ok=True)
        except Exception:
            pass

    log.info("PDF создан: %s (%d страниц)", output_path, len(jpeg_paths))
    return output_path
