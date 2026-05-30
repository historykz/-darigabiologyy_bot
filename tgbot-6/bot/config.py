"""
Конфигурация бота.
Читает переменные из .env файла.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Токен и Admins ───────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env!")

_admins_raw = os.getenv("ADMINS", "")
ADMINS: list[int] = [int(x.strip()) for x in _admins_raw.split(",") if x.strip().isdigit()]

# ─── Пути ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent

FILES_DIR      = BASE_DIR / "files"
CHECKLISTS_DIR = BASE_DIR / "checklists"
SUBMISSIONS_DIR= BASE_DIR / "submissions"
TEMP_DIR       = BASE_DIR / "temp"
LOGS_DIR       = BASE_DIR / "logs"
DB_PATH        = BASE_DIR / "bot.db"

# Создать все директории при импорте
for _d in (FILES_DIR, CHECKLISTS_DIR, SUBMISSIONS_DIR, TEMP_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ─── Временная зона ────────────────────────────────────────────────────────────
TIMEZONE = "Asia/Almaty"
