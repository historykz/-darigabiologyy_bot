"""
manage.py — утилиты управления ботом из командной строки.

Использование:
  python manage.py init_db              — создать/обновить таблицы
  python manage.py add_admin <tid>      — выдать роль admin по Telegram ID
  python manage.py list_users           — показать всех пользователей
  python manage.py list_curators        — показать всех кураторов
  python manage.py list_students        — показать всех учеников
  python manage.py backup               — создать резервную копию БД
  python manage.py stats                — общая статистика
"""

import asyncio
import sys
import shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bot.database import (
    init_db, UserRepo, CuratorRepo, StudentRepo,
    GroupRepo, WorkbookRepo, ChecklistRepo,
    SubmissionRepo, ExamBookingRepo
)
from bot.config import DB_PATH, ADMINS


async def cmd_init_db():
    await init_db()
    print("✅ База данных инициализирована")


async def cmd_add_admin(telegram_id: int):
    user = await UserRepo.get(telegram_id)
    if not user:
        print(f"❌ Пользователь {telegram_id} не найден. Сначала он должен написать /start боту.")
        return
    await UserRepo.set_role(telegram_id, "admin")
    await UserRepo.set_access(telegram_id, 1)
    print(f"✅ Пользователю {telegram_id} ({user['full_name']}) выдана роль admin")


async def cmd_list_users():
    users = await UserRepo.get_all()
    if not users:
        print("Нет пользователей в базе.")
        return
    print(f"\n{'ID':>12} | {'Роль':10} | {'Доступ':6} | {'Имя'}")
    print("-" * 60)
    for u in users:
        print(f"{u['telegram_id']:>12} | {u['role']:10} | {'Да' if u['has_access'] else 'Нет':6} | {u['full_name']}")
    print(f"\nВсего: {len(users)}")


async def cmd_list_curators():
    curators = await CuratorRepo.get_all()
    if not curators:
        print("Кураторов нет.")
        return
    print(f"\n{'ID':>5} | {'TG ID':>12} | {'Имя'}")
    print("-" * 50)
    for c in curators:
        print(f"{c['id']:>5} | {c['telegram_id']:>12} | {c['full_name']}")
    print(f"\nВсего: {len(curators)}")


async def cmd_list_students():
    students = await StudentRepo.get_all()
    if not students:
        print("Учеников нет.")
        return
    print(f"\n{'ID':>5} | {'TG ID':>12} | {'Группа':20} | {'Имя'}")
    print("-" * 70)
    for s in students:
        g = s['group_title'] if s['group_title'] else '—'
        print(f"{s['id']:>5} | {s['telegram_id']:>12} | {g:20} | {s['full_name']}")
    print(f"\nВсего: {len(students)}")


async def cmd_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"bot_{ts}.db"

    # Безопасная онлайн-копия через aiosqlite
    import aiosqlite
    async with aiosqlite.connect(str(DB_PATH)) as src:
        await src.backup(aiosqlite.connect(str(dest)))
    # Если выше не сработало — просто копируем файл
    if not dest.exists():
        shutil.copy2(DB_PATH, dest)
    print(f"✅ Резервная копия создана: {dest}")


async def cmd_stats():
    users = await UserRepo.get_all()
    curators = await CuratorRepo.get_all()
    students = await StudentRepo.get_all()
    groups = await GroupRepo.get_all()
    wbs = await WorkbookRepo.get_all()
    cls = await ChecklistRepo.get_all()
    subs = await SubmissionRepo.get_all()
    bookings = await ExamBookingRepo.get_all_for_export()

    print("\n" + "═" * 40)
    print("📊 СТАТИСТИКА БОТА")
    print("═" * 40)
    print(f"👤 Пользователей:       {len(users)}")
    print(f"👨‍🏫 Кураторов:           {len(curators)}")
    print(f"👨‍🎓 Учеников:            {len(students)}")
    print(f"👥 Групп:               {len(groups)}")
    print(f"📚 Рабочих тетрадей:    {len(wbs)}")
    print(f"✅ Чек-листов:          {len(cls)}")
    print(f"📥 Сдач РТ:             {len(subs)}")
    print(f"🗓 Записей на зачёт:    {len(bookings)}")

    db_size = Path(DB_PATH).stat().st_size if Path(DB_PATH).exists() else 0
    print(f"💾 Размер БД:           {db_size / 1024:.1f} KB")
    print("═" * 40)


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "init_db":
        await cmd_init_db()
    elif cmd == "add_admin":
        if len(sys.argv) < 3:
            print("Использование: python manage.py add_admin <telegram_id>")
            return
        await init_db()
        await cmd_add_admin(int(sys.argv[2]))
    elif cmd == "list_users":
        await init_db()
        await cmd_list_users()
    elif cmd == "list_curators":
        await init_db()
        await cmd_list_curators()
    elif cmd == "list_students":
        await init_db()
        await cmd_list_students()
    elif cmd == "backup":
        await cmd_backup()
    elif cmd == "stats":
        await init_db()
        await cmd_stats()
    else:
        print(f"Неизвестная команда: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
