"""
states.py — все FSM состояния для aiogram 3.
"""

from aiogram.fsm.state import State, StatesGroup


class AddWorkbook(StatesGroup):
    waiting_file  = State()
    waiting_title = State()


class DeleteWorkbook(StatesGroup):
    waiting_serial = State()


class RenameWorkbook(StatesGroup):
    waiting_serial   = State()
    waiting_new_name = State()


class AddChecklist(StatesGroup):
    waiting_file  = State()
    waiting_title = State()


class DeleteChecklist(StatesGroup):
    waiting_serial = State()


class GetWorkbook(StatesGroup):
    waiting_number = State()


class GetChecklist(StatesGroup):
    waiting_number = State()


class SubmitRT(StatesGroup):
    waiting_fullname  = State()
    collecting_photos = State()


class AddCurator(StatesGroup):
    waiting_telegram_id = State()
    waiting_fullname    = State()


class DeleteCurator(StatesGroup):
    waiting_curator_id = State()


class AddGroup(StatesGroup):
    waiting_title      = State()
    waiting_curator_id = State()


class AddStudent(StatesGroup):
    waiting_telegram_id = State()
    waiting_fullname    = State()
    waiting_group_id    = State()


class DeleteStudent(StatesGroup):
    waiting_student_id = State()


class GrantAccess(StatesGroup):
    waiting_telegram_id = State()


class RevokeAccess(StatesGroup):
    waiting_telegram_id = State()


class CreateExamSlots(StatesGroup):
    waiting_date     = State()
    waiting_start    = State()
    waiting_end      = State()
    waiting_duration = State()
    waiting_meet     = State()


class ExportFilter(StatesGroup):
    waiting_filter = State()


# ── Новые состояния для куратора ──────────────────────────────────────────────

class CuratorAddGroup(StatesGroup):
    """Куратор создаёт группу для себя."""
    waiting_title = State()


class CuratorAddStudent(StatesGroup):
    """Куратор добавляет ученика в свою группу."""
    waiting_telegram_id = State()
    waiting_fullname    = State()
    waiting_group_id    = State()


class CuratorDeleteStudent(StatesGroup):
    """Куратор удаляет своего ученика."""
    waiting_student_id = State()


class CuratorDeleteGroup(StatesGroup):
    """Куратор удаляет свою группу."""
    waiting_group_id = State()


# ── Массовое и гибкое добавление ─────────────────────────────────────────────

class AddAdminFlex(StatesGroup):
    """Добавить админа по ID или @username (одного или несколько)."""
    waiting_identifiers = State()


class BulkAddStudents(StatesGroup):
    """Массовое добавление учеников (до 15 человек)."""
    waiting_group_id    = State()
    waiting_identifiers = State()
    waiting_confirm     = State()


class BulkAddCurators(StatesGroup):
    """Массовое добавление кураторов."""
    waiting_identifiers = State()
    waiting_confirm     = State()


class AddStudentFlex(StatesGroup):
    """Добавить ученика по ID или @username (куратор)."""
    waiting_group_id   = State()
    waiting_identifier = State()
    waiting_fullname   = State()


class AddCuratorFlex(StatesGroup):
    """Добавить куратора по ID или @username."""
    waiting_identifier = State()
    waiting_fullname   = State()


# ── Практика ──────────────────────────────────────────────────────────────────

class SubmitPractice(StatesGroup):
    """Ученик отправляет скрины практики."""
    waiting_description = State()   # тема/описание (опционально)
    collecting_photos   = State()
