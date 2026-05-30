"""
keyboards.py — все клавиатуры бота (Reply + Inline).
"""

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


# ══════════════════════════════════════════════════════════════════════════════
# REPLY KEYBOARDS
# ══════════════════════════════════════════════════════════════════════════════

def main_menu_user() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="📚 Рабочие тетради")
    kb.button(text="📤 Сдать РТ")
    kb.button(text="✅ Чек-листы")
    kb.button(text="🗓 Запись на зачёт")
    kb.button(text="📋 Мои сдачи")
    kb.button(text="📸 Скрин практики")
    kb.button(text="📸 Мои практики")
    kb.button(text="👤 Мой профиль")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def main_menu_curator() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="📚 Рабочие тетради")
    kb.button(text="📤 Сдать РТ")
    kb.button(text="✅ Чек-листы")
    kb.button(text="🗓 Запись на зачёт")
    kb.button(text="📋 Мои сдачи")
    kb.button(text="📸 Скрин практики")
    kb.button(text="📸 Мои практики")
    kb.button(text="👤 Мой профиль")
    kb.button(text="👥 Мои группы")
    kb.button(text="👨‍🎓 Мои ученики")
    kb.button(text="📥 Сданные РТ")
    kb.button(text="📸 Практики учеников")
    kb.button(text="🗓 Создать слоты зачёта")
    kb.adjust(2, 2, 2, 2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def main_menu_admin() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="📚 Рабочие тетради")
    kb.button(text="📤 Сдать РТ")
    kb.button(text="✅ Чек-листы")
    kb.button(text="🗓 Запись на зачёт")
    kb.button(text="📋 Мои сдачи")
    kb.button(text="📸 Скрин практики")
    kb.button(text="📸 Мои практики")
    kb.button(text="👤 Мой профиль")
    kb.button(text="👥 Мои группы")
    kb.button(text="👨‍🎓 Мои ученики")
    kb.button(text="📥 Сданные РТ")
    kb.button(text="📸 Практики учеников")
    kb.button(text="🗓 Создать слоты зачёта")
    kb.button(text="⚙️ Админ-панель")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ Отмена")
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def submit_or_cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="📄 Отправить в PDF")
    kb.button(text="❌ Отменить")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN PANEL INLINE KEYBOARD
# ══════════════════════════════════════════════════════════════════════════════

def admin_panel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # РТ
    kb.button(text="➕ Добавить РТ",         callback_data="adm:wb:add")
    kb.button(text="📚 Список РТ",           callback_data="adm:wb:list")
    kb.button(text="🗑 Удалить РТ",          callback_data="adm:wb:del")
    kb.button(text="✏️ Переименовать РТ",    callback_data="adm:wb:rename")
    kb.button(text="🧹 Очистить все РТ",     callback_data="adm:wb:clear")
    # Доступ
    kb.button(text="➕ Выдать доступ",       callback_data="adm:acc:grant")
    kb.button(text="➖ Забрать доступ",      callback_data="adm:acc:revoke")
    kb.button(text="📋 Список с доступом",   callback_data="adm:acc:list")
    # Кураторы
    kb.button(text="👨‍🏫 Добавить куратора",      callback_data="adm:cur:add")
    kb.button(text="👨‍🏫 Массовое добавление",    callback_data="adm:cur:bulk")
    kb.button(text="👨‍🏫 Список кураторов",       callback_data="adm:cur:list")
    kb.button(text="🗑 Удалить куратора",        callback_data="adm:cur:del")
    # Группы
    kb.button(text="👥 Создать группу",      callback_data="adm:grp:add")
    kb.button(text="👥 Список групп",        callback_data="adm:grp:list")
    # Ученики
    kb.button(text="👨‍🎓 Добавить ученика",        callback_data="adm:stu:add")
    kb.button(text="👨‍🎓 Массовое добавление",     callback_data="adm:stu:bulk")
    kb.button(text="👨‍🎓 Список учеников",         callback_data="adm:stu:list")
    kb.button(text="🗑 Удалить ученика",          callback_data="adm:stu:del")
    # Сдачи РТ
    kb.button(text="📥 Все сдачи РТ",        callback_data="adm:sub:list")
    kb.button(text="🧹 Очистить сдачи РТ",   callback_data="adm:sub:clear")
    kb.button(text="📤 Экспорт сдач РТ",     callback_data="adm:exp:sub")
    kb.button(text="📤 Экспорт зачётов",     callback_data="adm:exp:exam")
    # Практики
    kb.button(text="📸 Все практики",        callback_data="adm:prac:list")
    kb.button(text="🧹 Очистить практики",   callback_data="adm:prac:clear")
    kb.button(text="📤 Экспорт практик",     callback_data="adm:exp:prac")
    # Чек-листы
    kb.button(text="➕ Добавить чек-лист",   callback_data="adm:cl:add")
    kb.button(text="📋 Список чек-листов",   callback_data="adm:cl:list")
    kb.button(text="🗑 Удалить чек-лист",    callback_data="adm:cl:del")
    kb.button(text="🧹 Очистить чек-листы",  callback_data="adm:cl:clear")
    kb.adjust(2, 2, 1,   # РТ: 5 кнопок
              3,          # Доступ: 3 кнопки
              3,          # Кураторы: 3 кнопки
              2,          # Группы: 2 кнопки
              3,          # Ученики: 3 кнопки
              2, 2,       # Сдачи: 4 кнопки
              2, 2)       # Чек-листы: 4 кнопки
    return kb.as_markup()


def confirm_clear_kb(action: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, очистить", callback_data=f"confirm:{action}")
    kb.button(text="❌ Отмена",       callback_data="confirm:cancel")
    kb.adjust(2)
    return kb.as_markup()


def back_to_admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад в панель", callback_data="adm:back")
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT FILTERS INLINE
# ══════════════════════════════════════════════════════════════════════════════

def export_filter_kb(prefix: str) -> InlineKeyboardMarkup:
    """prefix: sub | exam"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня",   callback_data=f"exp:{prefix}:today")
    kb.button(text="📆 Неделя",    callback_data=f"exp:{prefix}:week")
    kb.button(text="🗓 Месяц",     callback_data=f"exp:{prefix}:month")
    kb.button(text="📊 Всё время", callback_data=f"exp:{prefix}:all")
    kb.adjust(2)
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════════════════════
# EXAM SLOTS INLINE
# ══════════════════════════════════════════════════════════════════════════════

def exam_slots_kb(slots: list) -> InlineKeyboardMarkup:
    """slots — список aiosqlite.Row с полями id, slot_date, slot_time."""
    kb = InlineKeyboardBuilder()
    for s in slots:
        from bot.services.exam_service import format_date_for_display
        display = format_date_for_display(s["slot_date"])
        label = f"📅 {display}  🕐 {s['slot_time']}"
        kb.button(text=label, callback_data=f"book:{s['id']}")
    kb.button(text="❌ Отмена", callback_data="book:cancel")
    kb.adjust(1)
    return kb.as_markup()


def cancel_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить запись", callback_data=f"cancel_booking:{booking_id}")
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════════════════════
# GROUPS / STUDENTS INLINE
# ══════════════════════════════════════════════════════════════════════════════

def groups_list_kb(groups: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.button(text=f"👥 {g['title']}", callback_data=f"grp:{g['id']}")
    kb.adjust(1)
    return kb.as_markup()
