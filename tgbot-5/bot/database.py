"""
database.py — вся работа с SQLite через aiosqlite.
Паттерн: Repository (один класс на таблицу/домен).
"""

from __future__ import annotations

import aiosqlite
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from bot.config import DB_PATH

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# INIT DB
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username    TEXT,
    full_name   TEXT,
    role        TEXT DEFAULT 'user',   -- user | student | curator | admin
    has_access  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS workbooks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number INTEGER UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    file_id       TEXT,               -- Telegram file_id для кэширования
    created_at    TEXT DEFAULT (datetime('now','localtime')),
    added_by      INTEGER
);

CREATE TABLE IF NOT EXISTS checklists (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number    INTEGER UNIQUE NOT NULL,
    title            TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    file_type        TEXT NOT NULL,
    file_id          TEXT,
    created_at       TEXT DEFAULT (datetime('now','localtime')),
    added_by_admin_id INTEGER
);

CREATE TABLE IF NOT EXISTS curators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username    TEXT,
    full_name   TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    curator_id INTEGER NOT NULL REFERENCES curators(id) ON DELETE CASCADE,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username    TEXT,
    full_name   TEXT NOT NULL,
    curator_id  INTEGER REFERENCES curators(id) ON DELETE SET NULL,
    group_id    INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS submissions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL,
    curator_id       INTEGER,
    group_id         INTEGER,
    student_full_name TEXT NOT NULL,
    pdf_path         TEXT NOT NULL,
    submitted_at     TEXT DEFAULT (datetime('now','localtime')),
    status           TEXT DEFAULT 'submitted'
);

CREATE TABLE IF NOT EXISTS submission_photos_buffer (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    photo_path  TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS exam_slots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    curator_id          INTEGER NOT NULL REFERENCES curators(id) ON DELETE CASCADE,
    slot_date           TEXT NOT NULL,
    slot_time           TEXT NOT NULL,
    duration_minutes    INTEGER NOT NULL DEFAULT 15,
    google_meet_link    TEXT,
    is_booked           INTEGER DEFAULT 0,
    booked_by_student_id INTEGER,
    created_at          TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS practice_submissions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id        INTEGER NOT NULL,
    curator_id        INTEGER,
    group_id          INTEGER,
    student_full_name TEXT NOT NULL,
    description       TEXT,           -- тема/название практики (опционально)
    pdf_path          TEXT NOT NULL,
    submitted_at      TEXT DEFAULT (datetime('now','localtime')),
    status            TEXT DEFAULT 'submitted'
);

CREATE TABLE IF NOT EXISTS practice_photos_buffer (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    photo_path  TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS exam_bookings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id           INTEGER NOT NULL REFERENCES exam_slots(id) ON DELETE CASCADE,
    student_id        INTEGER NOT NULL,
    curator_id        INTEGER NOT NULL,
    group_id          INTEGER,
    student_full_name TEXT NOT NULL,
    booking_datetime  TEXT NOT NULL,
    google_meet_link  TEXT,
    status            TEXT DEFAULT 'active',   -- active | cancelled
    created_at        TEXT DEFAULT (datetime('now','localtime')),
    notified_10_min   INTEGER DEFAULT 0,
    notified_start    INTEGER DEFAULT 0
);
"""


async def init_db() -> None:
    """Инициализировать базу данных — создать таблицы если не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    log.info("База данных инициализирована: %s", DB_PATH)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _fetchone(query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            return await cur.fetchone()


async def _fetchall(query: str, params: tuple = ()) -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            return await cur.fetchall()


async def _execute(query: str, params: tuple = ()) -> int:
    """Выполнить INSERT/UPDATE/DELETE, вернуть lastrowid."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cur:
            await db.commit()
            return cur.lastrowid or 0


async def _executemany(query: str, params_list: list[tuple]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(query, params_list)
        await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# USERS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class UserRepo:

    @staticmethod
    async def upsert(telegram_id: int, username: Optional[str], full_name: str) -> None:
        """Создать или обновить пользователя."""
        await _execute(
            """INSERT INTO users (telegram_id, username, full_name)
               VALUES (?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 username=excluded.username,
                 full_name=excluded.full_name""",
            (telegram_id, username, full_name)
        )

    @staticmethod
    async def get(telegram_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))

    @staticmethod
    async def set_role(telegram_id: int, role: str) -> None:
        await _execute("UPDATE users SET role=? WHERE telegram_id=?", (role, telegram_id))

    @staticmethod
    async def set_access(telegram_id: int, has_access: int) -> None:
        await _execute("UPDATE users SET has_access=? WHERE telegram_id=?", (has_access, telegram_id))

    @staticmethod
    async def get_role(telegram_id: int) -> str:
        row = await _fetchone("SELECT role FROM users WHERE telegram_id=?", (telegram_id,))
        return row["role"] if row else "user"

    @staticmethod
    async def has_access(telegram_id: int) -> bool:
        row = await _fetchone("SELECT has_access, role FROM users WHERE telegram_id=?", (telegram_id,))
        if not row:
            return False
        if row["role"] in ("admin", "curator"):
            return True
        return bool(row["has_access"])

    @staticmethod
    async def get_all_with_access() -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM users WHERE has_access=1 ORDER BY full_name")

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM users ORDER BY created_at DESC")

    @staticmethod
    async def get_by_username(username: str) -> Optional[aiosqlite.Row]:
        """Поиск пользователя по username (без @)."""
        uname = username.lstrip("@").lower()
        return await _fetchone(
            "SELECT * FROM users WHERE LOWER(username)=?", (uname,)
        )

    @staticmethod
    async def resolve(identifier: str) -> Optional[aiosqlite.Row]:
        """
        Найти пользователя по Telegram ID (число) или @username.
        Возвращает Row или None.
        """
        identifier = identifier.strip()
        if identifier.startswith("@"):
            return await UserRepo.get_by_username(identifier[1:])
        if identifier.lstrip("-").isdigit():
            return await UserRepo.get(int(identifier))
        # Попробовать как username без @
        return await UserRepo.get_by_username(identifier)


# ══════════════════════════════════════════════════════════════════════════════
# WORKBOOKS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class WorkbookRepo:

    @staticmethod
    async def next_serial() -> int:
        row = await _fetchone("SELECT COALESCE(MAX(serial_number),0)+1 AS n FROM workbooks")
        return row["n"] if row else 1

    @staticmethod
    async def add(serial_number: int, title: str, file_path: str,
                  file_type: str, added_by: int) -> int:
        return await _execute(
            "INSERT INTO workbooks (serial_number,title,file_path,file_type,added_by) VALUES (?,?,?,?,?)",
            (serial_number, title, file_path, file_type, added_by)
        )

    @staticmethod
    async def get_by_serial(serial_number: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM workbooks WHERE serial_number=?", (serial_number,))

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM workbooks ORDER BY serial_number")

    @staticmethod
    async def delete(serial_number: int) -> Optional[aiosqlite.Row]:
        row = await _fetchone("SELECT * FROM workbooks WHERE serial_number=?", (serial_number,))
        if row:
            await _execute("DELETE FROM workbooks WHERE serial_number=?", (serial_number,))
        return row

    @staticmethod
    async def clear_all() -> list[aiosqlite.Row]:
        rows = await _fetchall("SELECT file_path FROM workbooks")
        await _execute("DELETE FROM workbooks")
        return rows

    @staticmethod
    async def update_file_id(serial_number: int, file_id: str) -> None:
        await _execute("UPDATE workbooks SET file_id=? WHERE serial_number=?", (file_id, serial_number))

    @staticmethod
    async def update_title(serial_number: int, new_title: str) -> None:
        await _execute("UPDATE workbooks SET title=? WHERE serial_number=?", (new_title, serial_number))


# ══════════════════════════════════════════════════════════════════════════════
# CHECKLISTS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class ChecklistRepo:

    @staticmethod
    async def next_serial() -> int:
        row = await _fetchone("SELECT COALESCE(MAX(serial_number),0)+1 AS n FROM checklists")
        return row["n"] if row else 1

    @staticmethod
    async def add(serial_number: int, title: str, file_path: str,
                  file_type: str, added_by: int) -> int:
        return await _execute(
            "INSERT INTO checklists (serial_number,title,file_path,file_type,added_by_admin_id) VALUES (?,?,?,?,?)",
            (serial_number, title, file_path, file_type, added_by)
        )

    @staticmethod
    async def get_by_serial(serial_number: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM checklists WHERE serial_number=?", (serial_number,))

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM checklists ORDER BY serial_number")

    @staticmethod
    async def delete(serial_number: int) -> Optional[aiosqlite.Row]:
        row = await _fetchone("SELECT * FROM checklists WHERE serial_number=?", (serial_number,))
        if row:
            await _execute("DELETE FROM checklists WHERE serial_number=?", (serial_number,))
        return row

    @staticmethod
    async def clear_all() -> list[aiosqlite.Row]:
        rows = await _fetchall("SELECT file_path FROM checklists")
        await _execute("DELETE FROM checklists")
        return rows

    @staticmethod
    async def update_file_id(serial_number: int, file_id: str) -> None:
        await _execute("UPDATE checklists SET file_id=? WHERE serial_number=?", (file_id, serial_number))


# ══════════════════════════════════════════════════════════════════════════════
# CURATORS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class CuratorRepo:

    @staticmethod
    async def add(telegram_id: int, username: Optional[str], full_name: str) -> int:
        return await _execute(
            "INSERT OR IGNORE INTO curators (telegram_id,username,full_name) VALUES (?,?,?)",
            (telegram_id, username, full_name)
        )

    @staticmethod
    async def get_by_tid(telegram_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM curators WHERE telegram_id=?", (telegram_id,))

    @staticmethod
    async def get_by_id(curator_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM curators WHERE id=?", (curator_id,))

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM curators ORDER BY full_name")

    @staticmethod
    async def delete(curator_id: int) -> None:
        await _execute("DELETE FROM curators WHERE id=?", (curator_id,))

    @staticmethod
    async def get_by_username(username: str) -> Optional[aiosqlite.Row]:
        uname = username.lstrip("@").lower()
        return await _fetchone("SELECT * FROM curators WHERE LOWER(username)=?", (uname,))


# ══════════════════════════════════════════════════════════════════════════════
# GROUPS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class GroupRepo:

    @staticmethod
    async def add(title: str, curator_id: int) -> int:
        return await _execute(
            "INSERT INTO groups (title,curator_id) VALUES (?,?)", (title, curator_id)
        )

    @staticmethod
    async def get_by_curator(curator_id: int) -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM groups WHERE curator_id=? ORDER BY title", (curator_id,))

    @staticmethod
    async def get_by_id(group_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM groups WHERE id=?", (group_id,))

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT g.*, c.full_name AS curator_name
               FROM groups g LEFT JOIN curators c ON g.curator_id=c.id
               ORDER BY g.title"""
        )

    @staticmethod
    async def delete(group_id: int) -> None:
        await _execute("DELETE FROM groups WHERE id=?", (group_id,))


# ══════════════════════════════════════════════════════════════════════════════
# STUDENTS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class StudentRepo:

    @staticmethod
    async def add(telegram_id: int, username: Optional[str], full_name: str,
                  curator_id: int, group_id: int) -> int:
        return await _execute(
            """INSERT OR IGNORE INTO students (telegram_id,username,full_name,curator_id,group_id)
               VALUES (?,?,?,?,?)""",
            (telegram_id, username, full_name, curator_id, group_id)
        )

    @staticmethod
    async def get_by_tid(telegram_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM students WHERE telegram_id=?", (telegram_id,))

    @staticmethod
    async def get_by_id(student_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM students WHERE id=?", (student_id,))

    @staticmethod
    async def get_by_group(group_id: int) -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM students WHERE group_id=? ORDER BY full_name", (group_id,))

    @staticmethod
    async def get_by_curator(curator_id: int) -> list[aiosqlite.Row]:
        return await _fetchall("SELECT * FROM students WHERE curator_id=? ORDER BY full_name", (curator_id,))

    @staticmethod
    async def get_all() -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT s.*, g.title AS group_title, c.full_name AS curator_name
               FROM students s
               LEFT JOIN groups g ON s.group_id=g.id
               LEFT JOIN curators c ON s.curator_id=c.id
               ORDER BY s.full_name"""
        )

    @staticmethod
    async def delete(student_id: int) -> None:
        await _execute("DELETE FROM students WHERE id=?", (student_id,))


# ══════════════════════════════════════════════════════════════════════════════
# SUBMISSIONS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class SubmissionRepo:

    @staticmethod
    async def add(student_id: int, curator_id: Optional[int], group_id: Optional[int],
                  student_full_name: str, pdf_path: str) -> int:
        return await _execute(
            """INSERT INTO submissions (student_id,curator_id,group_id,student_full_name,pdf_path)
               VALUES (?,?,?,?,?)""",
            (student_id, curator_id, group_id, student_full_name, pdf_path)
        )

    @staticmethod
    async def get_all(limit: int = 200) -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT sub.*, g.title AS group_title, c.full_name AS curator_name
               FROM submissions sub
               LEFT JOIN groups g ON sub.group_id=g.id
               LEFT JOIN curators c ON sub.curator_id=c.id
               ORDER BY sub.submitted_at DESC LIMIT ?""",
            (limit,)
        )

    @staticmethod
    async def get_by_curator(curator_id: int, limit: int = 200) -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT sub.*, g.title AS group_title
               FROM submissions sub
               LEFT JOIN groups g ON sub.group_id=g.id
               WHERE sub.curator_id=?
               ORDER BY sub.submitted_at DESC LIMIT ?""",
            (curator_id, limit)
        )

    @staticmethod
    async def get_today(curator_id: Optional[int] = None) -> list[aiosqlite.Row]:
        today = datetime.now().strftime("%Y-%m-%d")
        if curator_id:
            return await _fetchall(
                "SELECT * FROM submissions WHERE curator_id=? AND submitted_at LIKE ? ORDER BY submitted_at DESC",
                (curator_id, f"{today}%")
            )
        return await _fetchall(
            "SELECT * FROM submissions WHERE submitted_at LIKE ? ORDER BY submitted_at DESC",
            (f"{today}%",)
        )

    @staticmethod
    async def clear_all() -> None:
        await _execute("DELETE FROM submissions")

    @staticmethod
    async def get_by_id(submission_id: int) -> Optional[aiosqlite.Row]:
        """Получить конкретную сдачу по ID — используется при скачивании PDF."""
        return await _fetchone(
            """SELECT sub.*, g.title AS group_title, c.full_name AS curator_name
               FROM submissions sub
               LEFT JOIN groups g ON sub.group_id=g.id
               LEFT JOIN curators c ON sub.curator_id=c.id
               WHERE sub.id=?""",
            (submission_id,)
        )

    @staticmethod
    async def get_by_student_id(student_id: int, limit: int = 30) -> list[aiosqlite.Row]:
        """Сдачи конкретного ученика — для его личного просмотра."""
        return await _fetchall(
            """SELECT sub.*, g.title AS group_title, c.full_name AS curator_name
               FROM submissions sub
               LEFT JOIN groups g ON sub.group_id=g.id
               LEFT JOIN curators c ON sub.curator_id=c.id
               WHERE sub.student_id=?
               ORDER BY sub.submitted_at DESC LIMIT ?""",
            (student_id, limit)
        )

    @staticmethod
    async def get_filtered(period: str, curator_id: Optional[int] = None,
                           group_id: Optional[int] = None) -> list[aiosqlite.Row]:
        """period: today|week|month|all"""
        conditions = []
        params: list = []
        now = datetime.now()

        if period == "today":
            conditions.append("DATE(sub.submitted_at)=DATE('now','localtime')")
        elif period == "week":
            conditions.append("sub.submitted_at >= datetime('now','-7 days','localtime')")
        elif period == "month":
            conditions.append("sub.submitted_at >= datetime('now','-30 days','localtime')")

        if curator_id:
            conditions.append("sub.curator_id=?")
            params.append(curator_id)
        if group_id:
            conditions.append("sub.group_id=?")
            params.append(group_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""SELECT sub.*, g.title AS group_title, c.full_name AS curator_name
                    FROM submissions sub
                    LEFT JOIN groups g ON sub.group_id=g.id
                    LEFT JOIN curators c ON sub.curator_id=c.id
                    {where}
                    ORDER BY sub.submitted_at DESC"""
        return await _fetchall(query, tuple(params))


# ══════════════════════════════════════════════════════════════════════════════
# PHOTO BUFFER REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class PhotoBufferRepo:

    @staticmethod
    async def add(student_id: int, photo_path: str, order_index: int) -> None:
        await _execute(
            "INSERT INTO submission_photos_buffer (student_id,photo_path,order_index) VALUES (?,?,?)",
            (student_id, photo_path, order_index)
        )

    @staticmethod
    async def get_by_student(student_id: int) -> list[aiosqlite.Row]:
        return await _fetchall(
            "SELECT * FROM submission_photos_buffer WHERE student_id=? ORDER BY order_index",
            (student_id,)
        )

    @staticmethod
    async def count(student_id: int) -> int:
        row = await _fetchone(
            "SELECT COUNT(*) AS c FROM submission_photos_buffer WHERE student_id=?",
            (student_id,)
        )
        return row["c"] if row else 0

    @staticmethod
    async def clear(student_id: int) -> None:
        await _execute("DELETE FROM submission_photos_buffer WHERE student_id=?", (student_id,))

    @staticmethod
    async def next_order(student_id: int) -> int:
        row = await _fetchone(
            "SELECT COALESCE(MAX(order_index),0)+1 AS n FROM submission_photos_buffer WHERE student_id=?",
            (student_id,)
        )
        return row["n"] if row else 1


# ══════════════════════════════════════════════════════════════════════════════
# EXAM SLOTS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class ExamSlotRepo:

    @staticmethod
    async def add_many(curator_id: int, slot_date: str, slots: list[str],
                       duration: int, meet_link: str) -> None:
        params = [(curator_id, slot_date, t, duration, meet_link) for t in slots]
        await _executemany(
            "INSERT INTO exam_slots (curator_id,slot_date,slot_time,duration_minutes,google_meet_link) VALUES (?,?,?,?,?)",
            params
        )

    @staticmethod
    async def get_free_by_curator(curator_id: int) -> list[aiosqlite.Row]:
        """Все свободные слоты куратора начиная с сегодня (все дни)."""
        today = datetime.now().strftime("%Y-%m-%d")
        return await _fetchall(
            """SELECT * FROM exam_slots
               WHERE curator_id=? AND is_booked=0
               AND (slot_date > ? OR (slot_date=? AND slot_time >= time('now','localtime')))
               ORDER BY slot_date, slot_time""",
            (curator_id, today, today)
        )

    @staticmethod
    async def get_free_dates_by_curator(curator_id: int) -> list[str]:
        """Уникальные даты со свободными слотами (для выбора дня)."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = await _fetchall(
            """SELECT DISTINCT slot_date FROM exam_slots
               WHERE curator_id=? AND is_booked=0
               AND (slot_date > ? OR (slot_date=? AND slot_time >= time('now','localtime')))
               ORDER BY slot_date""",
            (curator_id, today, today)
        )
        return [r["slot_date"] for r in rows]

    @staticmethod
    async def get_free_by_curator_and_date(curator_id: int, slot_date: str) -> list[aiosqlite.Row]:
        """Свободные слоты куратора на конкретную дату."""
        return await _fetchall(
            """SELECT * FROM exam_slots
               WHERE curator_id=? AND is_booked=0 AND slot_date=?
               ORDER BY slot_time""",
            (curator_id, slot_date)
        )

    @staticmethod
    async def get_by_id(slot_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone("SELECT * FROM exam_slots WHERE id=?", (slot_id,))

    @staticmethod
    async def book(slot_id: int, student_id: int) -> None:
        await _execute(
            "UPDATE exam_slots SET is_booked=1, booked_by_student_id=? WHERE id=?",
            (student_id, slot_id)
        )

    @staticmethod
    async def unbook(slot_id: int) -> None:
        await _execute(
            "UPDATE exam_slots SET is_booked=0, booked_by_student_id=NULL WHERE id=?",
            (slot_id,)
        )

    @staticmethod
    async def get_upcoming_unnotified() -> list[aiosqlite.Row]:
        """Слоты за ближайшие 11 минут для рассылки уведомлений."""
        return await _fetchall(
            """SELECT es.*, eb.id AS booking_id, eb.student_id, eb.student_full_name,
                      eb.google_meet_link AS meet_link, eb.notified_10_min, eb.notified_start
               FROM exam_slots es
               JOIN exam_bookings eb ON eb.slot_id=es.id AND eb.status='active'
               WHERE es.is_booked=1
               AND datetime(es.slot_date||' '||es.slot_time) BETWEEN
                   datetime('now','localtime') AND datetime('now','localtime','+11 minutes')"""
        )


# ══════════════════════════════════════════════════════════════════════════════
# EXAM BOOKINGS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class ExamBookingRepo:

    @staticmethod
    async def add(slot_id: int, student_id: int, curator_id: int,
                  group_id: Optional[int], student_full_name: str,
                  booking_datetime: str, meet_link: str) -> int:
        return await _execute(
            """INSERT INTO exam_bookings
               (slot_id,student_id,curator_id,group_id,student_full_name,booking_datetime,google_meet_link)
               VALUES (?,?,?,?,?,?,?)""",
            (slot_id, student_id, curator_id, group_id, student_full_name, booking_datetime, meet_link)
        )

    @staticmethod
    async def get_active_by_student(student_id: int) -> Optional[aiosqlite.Row]:
        return await _fetchone(
            """SELECT eb.*, es.slot_date, es.slot_time, es.duration_minutes,
                      c.full_name AS curator_name
               FROM exam_bookings eb
               JOIN exam_slots es ON eb.slot_id=es.id
               JOIN curators c ON eb.curator_id=c.id
               WHERE eb.student_id=? AND eb.status='active'
               ORDER BY eb.created_at DESC LIMIT 1""",
            (student_id,)
        )

    @staticmethod
    async def cancel(booking_id: int) -> None:
        await _execute("UPDATE exam_bookings SET status='cancelled' WHERE id=?", (booking_id,))

    @staticmethod
    async def get_by_curator(curator_id: int) -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT eb.*, es.slot_date, es.slot_time
               FROM exam_bookings eb
               JOIN exam_slots es ON eb.slot_id=es.id
               WHERE eb.curator_id=? AND eb.status='active'
               ORDER BY es.slot_date, es.slot_time""",
            (curator_id,)
        )

    @staticmethod
    async def set_notified(booking_id: int, field: str) -> None:
        """field: notified_10_min | notified_start"""
        await _execute(f"UPDATE exam_bookings SET {field}=1 WHERE id=?", (booking_id,))

    @staticmethod
    async def get_all_for_export() -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT eb.*, es.slot_date, es.slot_time, g.title AS group_title,
                      c.full_name AS curator_name
               FROM exam_bookings eb
               JOIN exam_slots es ON eb.slot_id=es.id
               LEFT JOIN groups g ON eb.group_id=g.id
               LEFT JOIN curators c ON eb.curator_id=c.id
               ORDER BY es.slot_date, es.slot_time"""
        )


# ══════════════════════════════════════════════════════════════════════════════
# PRACTICE SUBMISSIONS REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class PracticeRepo:
    """Сдачи скринов практики."""

    @staticmethod
    async def add(student_id: int, curator_id: Optional[int], group_id: Optional[int],
                  student_full_name: str, pdf_path: str, description: str = "") -> int:
        return await _execute(
            """INSERT INTO practice_submissions
               (student_id,curator_id,group_id,student_full_name,pdf_path,description)
               VALUES (?,?,?,?,?,?)""",
            (student_id, curator_id, group_id, student_full_name, pdf_path, description)
        )

    @staticmethod
    async def get_by_id(submission_id: int) -> Optional[aiosqlite.Row]:
        """Получить конкретную сдачу по ID — используется при скачивании PDF."""
        return await _fetchone(
            """SELECT sub.*, g.title AS group_title, c.full_name AS curator_name
               FROM submissions sub
               LEFT JOIN groups g ON sub.group_id=g.id
               LEFT JOIN curators c ON sub.curator_id=c.id
               WHERE sub.id=?""",
            (submission_id,)
        )

    @staticmethod
    async def get_by_id(practice_id: int) -> Optional[aiosqlite.Row]:
        """Получить конкретную практику по ID."""
        return await _fetchone(
            """SELECT p.*, g.title AS group_title, c.full_name AS curator_name
               FROM practice_submissions p
               LEFT JOIN groups g ON p.group_id=g.id
               LEFT JOIN curators c ON p.curator_id=c.id
               WHERE p.id=?""",
            (practice_id,)
        )

    @staticmethod
    async def get_by_student_id(student_id: int, limit: int = 30) -> list[aiosqlite.Row]:
        """Все практики конкретного ученика."""
        return await _fetchall(
            """SELECT p.*, g.title AS group_title, c.full_name AS curator_name
               FROM practice_submissions p
               LEFT JOIN groups g ON p.group_id=g.id
               LEFT JOIN curators c ON p.curator_id=c.id
               WHERE p.student_id=?
               ORDER BY p.submitted_at DESC LIMIT ?""",
            (student_id, limit)
        )

    @staticmethod
    async def get_by_curator(curator_id: int, limit: int = 200) -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT p.*, g.title AS group_title
               FROM practice_submissions p
               LEFT JOIN groups g ON p.group_id=g.id
               WHERE p.curator_id=?
               ORDER BY p.submitted_at DESC LIMIT ?""",
            (curator_id, limit)
        )

    @staticmethod
    async def get_all(limit: int = 200) -> list[aiosqlite.Row]:
        return await _fetchall(
            """SELECT p.*, g.title AS group_title, c.full_name AS curator_name
               FROM practice_submissions p
               LEFT JOIN groups g ON p.group_id=g.id
               LEFT JOIN curators c ON p.curator_id=c.id
               ORDER BY p.submitted_at DESC LIMIT ?""",
            (limit,)
        )

    @staticmethod
    async def get_filtered(period: str, curator_id: Optional[int] = None,
                           group_id: Optional[int] = None) -> list[aiosqlite.Row]:
        conditions, params = [], []
        if period == "today":
            conditions.append("DATE(p.submitted_at)=DATE('now','localtime')")
        elif period == "week":
            conditions.append("p.submitted_at >= datetime('now','-7 days','localtime')")
        elif period == "month":
            conditions.append("p.submitted_at >= datetime('now','-30 days','localtime')")
        if curator_id:
            conditions.append("p.curator_id=?"); params.append(curator_id)
        if group_id:
            conditions.append("p.group_id=?"); params.append(group_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return await _fetchall(
            f"""SELECT p.*, g.title AS group_title, c.full_name AS curator_name
                FROM practice_submissions p
                LEFT JOIN groups g ON p.group_id=g.id
                LEFT JOIN curators c ON p.curator_id=c.id
                {where} ORDER BY p.submitted_at DESC""",
            tuple(params)
        )

    @staticmethod
    async def clear_all() -> None:
        await _execute("DELETE FROM practice_submissions")


class PracticePhotoRepo:
    """Буфер фото для практики."""

    @staticmethod
    async def add(student_id: int, photo_path: str, order_index: int) -> None:
        await _execute(
            "INSERT INTO practice_photos_buffer (student_id,photo_path,order_index) VALUES (?,?,?)",
            (student_id, photo_path, order_index)
        )

    @staticmethod
    async def get_by_student(student_id: int) -> list[aiosqlite.Row]:
        return await _fetchall(
            "SELECT * FROM practice_photos_buffer WHERE student_id=? ORDER BY order_index",
            (student_id,)
        )

    @staticmethod
    async def count(student_id: int) -> int:
        row = await _fetchone(
            "SELECT COUNT(*) AS c FROM practice_photos_buffer WHERE student_id=?",
            (student_id,)
        )
        return row["c"] if row else 0

    @staticmethod
    async def next_order(student_id: int) -> int:
        row = await _fetchone(
            "SELECT COALESCE(MAX(order_index),0)+1 AS n FROM practice_photos_buffer WHERE student_id=?",
            (student_id,)
        )
        return row["n"] if row else 1

    @staticmethod
    async def clear(student_id: int) -> None:
        await _execute("DELETE FROM practice_photos_buffer WHERE student_id=?", (student_id,))
