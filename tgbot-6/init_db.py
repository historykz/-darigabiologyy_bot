"""
init_db.py — запустите один раз для создания базы данных.
Использование: python init_db.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bot.database import init_db


async def main():
    print("Инициализация базы данных...")
    await init_db()
    print("✅ База данных создана успешно!")


if __name__ == "__main__":
    asyncio.run(main())
