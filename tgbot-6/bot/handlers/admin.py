"""
handlers/admin.py
Полная админ-панель: управление РТ, чек-листами, кураторами,
учениками, группами, доступами, экспортом.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile

from bot.config import FILES_DIR, CHECKLISTS_DIR
from bot.database import (
    UserRepo, WorkbookRepo, ChecklistRepo,
    CuratorRepo, GroupRepo, StudentRepo,
    SubmissionRepo, ExamBookingRepo, PracticeRepo
)
from bot.filters.roles import IsAdmin
from bot.keyboards import (
    admin_panel_kb, confirm_clear_kb, back_to_admin_kb, export_filter_kb
)
from bot.services.file_service import save_telegram_file, get_file_extension, get_file_type
from bot.services.excel_service import export_submissions, export_exam_bookings, export_practices
from bot.states import (
    AddWorkbook, DeleteWorkbook, RenameWorkbook,
    AddChecklist, DeleteChecklist,
    AddCurator, DeleteCurator,
    AddGroup, AddStudent, DeleteStudent,
    GrantAccess, RevokeAccess,
    AddAdminFlex, BulkAddStudents, BulkAddCurators, AddCuratorFlex
)
from bot.utils.helpers import now_str, safe_filename
from bot.utils.identifier import parse_identifiers, format_identifier_list

log = logging.getLogger(__name__)
router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ══════════════════════════════════════════════════════════════════════════════
# ОТКРЫТИЕ ПАНЕЛИ
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "⚙️ Админ-панель")
@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "⚙️ <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_panel_kb()
    )


@router.callback_query(F.data == "adm:back")
async def adm_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_panel_kb()
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# РАБОЧИЕ ТЕТРАДИ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:wb:add")
async def adm_wb_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "📎 Отправьте файл рабочей тетради (PDF, DOCX, фото и т.д.):"
    )
    await state.set_state(AddWorkbook.waiting_file)
    await callback.answer()


@router.message(AddWorkbook.waiting_file)
async def adm_wb_file(message: Message, state: FSMContext, bot: Bot) -> None:
    file_id, ext = get_file_extension(message)
    if not file_id:
        await message.answer("⚠️ Отправьте файл (документ, фото и т.д.).")
        return

    serial = await WorkbookRepo.next_serial()
    filename = f"wb_{serial}_{now_str()}{ext}"
    path = await save_telegram_file(bot, file_id, str(FILES_DIR), filename)

    await state.update_data(file_path=path, file_type=get_file_type(ext), serial=serial)
    await message.answer("✏️ Теперь введите <b>название / тему</b> рабочей тетради:", parse_mode="HTML")
    await state.set_state(AddWorkbook.waiting_title)


@router.message(AddWorkbook.waiting_title)
async def adm_wb_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("⚠️ Название не может быть пустым.")
        return

    data = await state.get_data()
    uid  = message.from_user.id

    await WorkbookRepo.add(
        serial_number=data["serial"],
        title=title,
        file_path=data["file_path"],
        file_type=data["file_type"],
        added_by=uid
    )
    await state.clear()
    await message.answer(
        f"✅ <b>Рабочая тетрадь добавлена</b>\n\n"
        f"Серийный номер: №{data['serial']}\n"
        f"Название: {title}",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )


@router.callback_query(F.data == "adm:wb:list")
async def adm_wb_list(callback: CallbackQuery) -> None:
    wbs = await WorkbookRepo.get_all()
    if not wbs:
        await callback.message.answer("📭 Рабочих тетрадей нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    lines = ["📚 <b>Список рабочих тетрадей:</b>\n"]
    for wb in wbs:
        lines.append(f"№{wb['serial_number']} — {wb['title']} [{wb['file_type']}]")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:wb:del")
async def adm_wb_del_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("🗑 Введите серийный номер РТ для удаления:")
    await state.set_state(DeleteWorkbook.waiting_serial)
    await callback.answer()


@router.message(DeleteWorkbook.waiting_serial)
async def adm_wb_del(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите число.")
        return

    serial = int(text)
    row = await WorkbookRepo.delete(serial)
    await state.clear()

    if not row:
        await message.answer(f"❌ РТ №{serial} не найдена.", reply_markup=back_to_admin_kb())
        return

    # Удалить файл
    try:
        Path(row["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass

    await message.answer(f"✅ РТ №{serial} удалена.", reply_markup=back_to_admin_kb())


@router.callback_query(F.data == "adm:wb:rename")
async def adm_wb_rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("✏️ Введите серийный номер РТ для переименования:")
    await state.set_state(RenameWorkbook.waiting_serial)
    await callback.answer()


@router.message(RenameWorkbook.waiting_serial)
async def adm_wb_rename_serial(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите число.")
        return
    serial = int(text)
    wb = await WorkbookRepo.get_by_serial(serial)
    if not wb:
        await message.answer(f"❌ РТ №{serial} не найдена.")
        await state.clear()
        return
    await state.update_data(serial=serial)
    await message.answer(f"Текущее название: <b>{wb['title']}</b>\nВведите новое название:", parse_mode="HTML")
    await state.set_state(RenameWorkbook.waiting_new_name)


@router.message(RenameWorkbook.waiting_new_name)
async def adm_wb_rename_name(message: Message, state: FSMContext) -> None:
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("⚠️ Название не может быть пустым.")
        return
    data = await state.get_data()
    await WorkbookRepo.update_title(data["serial"], new_name)
    await state.clear()
    await message.answer(
        f"✅ Название РТ №{data['serial']} изменено на: <b>{new_name}</b>",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )


@router.callback_query(F.data == "adm:wb:clear")
async def adm_wb_clear_confirm(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "⚠️ <b>Вы точно хотите удалить все рабочие тетради?</b>\nЭто действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=confirm_clear_kb("wb_clear")
    )
    await callback.answer()


@router.callback_query(F.data == "confirm:wb_clear")
async def adm_wb_clear_do(callback: CallbackQuery) -> None:
    rows = await WorkbookRepo.clear_all()
    for r in rows:
        try:
            Path(r["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    await callback.message.edit_text(
        f"✅ Удалено рабочих тетрадей: {len(rows)}",
        reply_markup=back_to_admin_kb()
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ЧЕК-ЛИСТЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:cl:add")
async def adm_cl_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("📎 Отправьте файл чек-листа:")
    await state.set_state(AddChecklist.waiting_file)
    await callback.answer()


@router.message(AddChecklist.waiting_file)
async def adm_cl_file(message: Message, state: FSMContext, bot: Bot) -> None:
    file_id, ext = get_file_extension(message)
    if not file_id:
        await message.answer("⚠️ Отправьте файл.")
        return

    serial = await ChecklistRepo.next_serial()
    filename = f"cl_{serial}_{now_str()}{ext}"
    path = await save_telegram_file(bot, file_id, str(CHECKLISTS_DIR), filename)

    await state.update_data(file_path=path, file_type=get_file_type(ext), serial=serial)
    await message.answer("✏️ Введите <b>название</b> чек-листа:", parse_mode="HTML")
    await state.set_state(AddChecklist.waiting_title)


@router.message(AddChecklist.waiting_title)
async def adm_cl_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("⚠️ Название не может быть пустым.")
        return

    data = await state.get_data()
    uid  = message.from_user.id

    await ChecklistRepo.add(
        serial_number=data["serial"],
        title=title,
        file_path=data["file_path"],
        file_type=data["file_type"],
        added_by=uid
    )
    await state.clear()
    await message.answer(
        f"✅ <b>Чек-лист добавлен</b>\n\n"
        f"Серийный номер: №{data['serial']}\n"
        f"Название: {title}",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )


@router.callback_query(F.data == "adm:cl:list")
async def adm_cl_list(callback: CallbackQuery) -> None:
    cls = await ChecklistRepo.get_all()
    if not cls:
        await callback.message.answer("📭 Чек-листов нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    lines = ["✅ <b>Список чек-листов:</b>\n"]
    for cl in cls:
        lines.append(f"№{cl['serial_number']} — {cl['title']} [{cl['file_type']}]")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:cl:del")
async def adm_cl_del_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("🗑 Введите серийный номер чек-листа для удаления:")
    await state.set_state(DeleteChecklist.waiting_serial)
    await callback.answer()


@router.message(DeleteChecklist.waiting_serial)
async def adm_cl_del(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите число.")
        return
    serial = int(text)
    row = await ChecklistRepo.delete(serial)
    await state.clear()
    if not row:
        await message.answer(f"❌ Чек-лист №{serial} не найден.", reply_markup=back_to_admin_kb())
        return
    try:
        Path(row["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    await message.answer(f"✅ Чек-лист №{serial} удалён.", reply_markup=back_to_admin_kb())


@router.callback_query(F.data == "adm:cl:clear")
async def adm_cl_clear_confirm(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "⚠️ <b>Удалить все чек-листы?</b>",
        parse_mode="HTML",
        reply_markup=confirm_clear_kb("cl_clear")
    )
    await callback.answer()


@router.callback_query(F.data == "confirm:cl_clear")
async def adm_cl_clear_do(callback: CallbackQuery) -> None:
    rows = await ChecklistRepo.clear_all()
    for r in rows:
        try:
            Path(r["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    await callback.message.edit_text(f"✅ Удалено чек-листов: {len(rows)}", reply_markup=back_to_admin_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ДОСТУП
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:acc:grant")
async def adm_acc_grant_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "➕ Введите <b>Telegram ID</b> пользователя для выдачи доступа:",
        parse_mode="HTML"
    )
    await state.set_state(GrantAccess.waiting_telegram_id)
    await callback.answer()


@router.message(GrantAccess.waiting_telegram_id)
async def adm_acc_grant_do(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите числовой Telegram ID.")
        return
    tid = int(text)
    user = await UserRepo.get(tid)
    if not user:
        await message.answer(f"❌ Пользователь {tid} не найден в базе. Он должен написать /start боту.")
        await state.clear()
        return
    await UserRepo.set_access(tid, 1)
    await state.clear()
    await message.answer(
        f"✅ Доступ выдан: <b>{user['full_name']}</b> (ID: {tid})",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )
    # ── Уведомление пользователю ──────────────────────────────────────────
    try:
        await bot.send_message(
            tid,
            f"✅ <b>Вам выдан доступ к материалам!</b>\n\n"
            f"Теперь вам доступно:\n"
            f"📚 Рабочие тетради\n"
            f"✅ Чек-листы\n"
            f"📤 Сдача РТ\n"
            f"🗓 Запись на зачёт\n\n"
            f"Нажмите /start чтобы открыть меню.",
            parse_mode="HTML"
        )
    except Exception as e:
        log.warning("Не удалось уведомить пользователя %s: %s", tid, e)


@router.callback_query(F.data == "adm:acc:revoke")
async def adm_acc_revoke_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("➖ Введите <b>Telegram ID</b> для отзыва доступа:", parse_mode="HTML")
    await state.set_state(RevokeAccess.waiting_telegram_id)
    await callback.answer()


@router.message(RevokeAccess.waiting_telegram_id)
async def adm_acc_revoke_do(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите числовой Telegram ID.")
        return
    tid = int(text)
    user_r = await UserRepo.get(tid)
    await UserRepo.set_access(tid, 0)
    await state.clear()
    await message.answer(f"✅ Доступ отозван у ID: {tid}", reply_markup=back_to_admin_kb())
    # ── Уведомление пользователю ──────────────────────────────────────────
    try:
        await bot.send_message(
            tid,
            "ℹ️ Ваш доступ к материалам был отозван администратором.\n"
            "По вопросам обратитесь к куратору.",
        )
    except Exception as e:
        log.warning("Не удалось уведомить пользователя %s: %s", tid, e)


@router.callback_query(F.data == "adm:acc:list")
async def adm_acc_list(callback: CallbackQuery) -> None:
    users = await UserRepo.get_all_with_access()
    if not users:
        await callback.message.answer("📭 Нет пользователей с доступом.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    lines = [f"📋 <b>Пользователи с доступом ({len(users)}):</b>\n"]
    for u in users:
        uname = f"@{u['username']}" if u["username"] else "—"
        lines.append(f"• {u['full_name']} ({uname}) — ID: <code>{u['telegram_id']}</code>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# КУРАТОРЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:cur:add")
async def adm_cur_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "👨‍🏫 Введите <b>Telegram ID</b> нового куратора:\n"
        "(Куратор должен сначала написать /start боту)",
        parse_mode="HTML"
    )
    await state.set_state(AddCurator.waiting_telegram_id)
    await callback.answer()


@router.message(AddCurator.waiting_telegram_id)
async def adm_cur_tid(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите числовой Telegram ID.")
        return
    tid = int(text)
    user = await UserRepo.get(tid)
    if not user:
        await message.answer(f"❌ Пользователь {tid} не найден. Он должен написать /start.")
        await state.clear()
        return
    await state.update_data(tid=tid, username=user["username"], auto_name=user["full_name"])
    await message.answer(
        f"Имя в базе: <b>{user['full_name']}</b>\n"
        f"Введите <b>отображаемое имя куратора</b> (или нажмите Enter для подтверждения):\n"
        f"Отправьте имя или <code>+</code> для использования текущего.",
        parse_mode="HTML"
    )
    await state.set_state(AddCurator.waiting_fullname)


@router.message(AddCurator.waiting_fullname)
async def adm_cur_name(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    text = (message.text or "").strip()
    fullname = data["auto_name"] if text == "+" else text

    if not fullname:
        await message.answer("⚠️ Введите имя или отправьте +")
        return

    tid = data["tid"]
    await CuratorRepo.add(tid, data.get("username"), fullname)
    await UserRepo.set_role(tid, "curator")
    await UserRepo.set_access(tid, 1)
    await state.clear()

    await message.answer(
        f"✅ Куратор добавлен: <b>{fullname}</b>\n"
        f"ID: <code>{tid}</code>",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )
    # ── Уведомление новому куратору ────────────────────────────────────────
    try:
        await bot.send_message(
            tid,
            f"👨‍🏫 <b>Вы назначены куратором!</b>\n\n"
            f"Вам открыты расширенные возможности:\n"
            f"👥 Создание групп\n"
            f"👨‍🎓 Добавление учеников\n"
            f"📥 Просмотр сданных РТ\n"
            f"🗓 Создание слотов для зачётов\n"
            f"📩 Получение PDF от учеников\n\n"
            f"Нажмите /start чтобы открыть меню куратора.",
            parse_mode="HTML"
        )
    except Exception as e:
        log.warning("Не удалось уведомить куратора %s: %s", tid, e)


@router.callback_query(F.data == "adm:cur:list")
async def adm_cur_list(callback: CallbackQuery) -> None:
    curators = await CuratorRepo.get_all()
    if not curators:
        await callback.message.answer("📭 Кураторов нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    lines = [f"👨‍🏫 <b>Кураторы ({len(curators)}):</b>\n"]
    for c in curators:
        uname = f"@{c['username']}" if c["username"] else "—"
        lines.append(f"• [ID:{c['id']}] {c['full_name']} ({uname}) | TG: <code>{c['telegram_id']}</code>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:cur:del")
async def adm_cur_del_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("🗑 Введите <b>ID куратора</b> (из списка кураторов) для удаления:", parse_mode="HTML")
    await state.set_state(DeleteCurator.waiting_curator_id)
    await callback.answer()


@router.message(DeleteCurator.waiting_curator_id)
async def adm_cur_del_do(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите ID куратора (число).")
        return
    cid = int(text)
    curator = await CuratorRepo.get_by_id(cid)
    if not curator:
        await message.answer("❌ Куратор не найден.")
        await state.clear()
        return
    await CuratorRepo.delete(cid)
    await UserRepo.set_role(curator["telegram_id"], "user")
    await state.clear()
    await message.answer(
        f"✅ Куратор <b>{curator['full_name']}</b> удалён.",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )


# ══════════════════════════════════════════════════════════════════════════════
# ГРУППЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:grp:add")
async def adm_grp_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    curators = await CuratorRepo.get_all()
    if not curators:
        await callback.message.answer("⚠️ Сначала добавьте куратора.")
        await callback.answer()
        return
    lines = ["👨‍🏫 Введите <b>ID куратора</b> для группы:\n"]
    for c in curators:
        lines.append(f"[ID:{c['id']}] {c['full_name']}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(AddGroup.waiting_curator_id)
    await callback.answer()


@router.message(AddGroup.waiting_curator_id)
async def adm_grp_curator(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите ID куратора.")
        return
    cid = int(text)
    curator = await CuratorRepo.get_by_id(cid)
    if not curator:
        await message.answer("❌ Куратор не найден.")
        return
    await state.update_data(curator_id=cid, curator_name=curator["full_name"])
    await message.answer(f"Куратор: <b>{curator['full_name']}</b>\nВведите <b>название группы</b>:", parse_mode="HTML")
    await state.set_state(AddGroup.waiting_title)


@router.message(AddGroup.waiting_title)
async def adm_grp_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("⚠️ Введите название.")
        return
    data = await state.get_data()
    gid = await GroupRepo.add(title, data["curator_id"])
    await state.clear()
    await message.answer(
        f"✅ Группа создана: <b>{title}</b>\n"
        f"Куратор: {data['curator_name']}\n"
        f"ID группы: {gid}",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )


@router.callback_query(F.data == "adm:grp:list")
async def adm_grp_list(callback: CallbackQuery) -> None:
    groups = await GroupRepo.get_all()
    if not groups:
        await callback.message.answer("📭 Групп нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return
    lines = [f"👥 <b>Группы ({len(groups)}):</b>\n"]
    for g in groups:
        curator_name = g.get("curator_name") or "—"
        lines.append(f"[ID:{g['id']}] {g['title']} → {curator_name}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# УЧЕНИКИ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:stu:add")
async def adm_stu_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "👨‍🎓 Введите <b>Telegram ID</b> ученика:\n"
        "(Ученик должен написать /start боту)",
        parse_mode="HTML"
    )
    await state.set_state(AddStudent.waiting_telegram_id)
    await callback.answer()


@router.message(AddStudent.waiting_telegram_id)
async def adm_stu_tid(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите числовой Telegram ID.")
        return
    tid = int(text)
    user = await UserRepo.get(tid)
    if not user:
        await message.answer(f"❌ Пользователь {tid} не найден. Он должен написать /start.")
        await state.clear()
        return

    # Показать группы для выбора
    groups = await GroupRepo.get_all()
    if not groups:
        await message.answer("⚠️ Сначала создайте группу.")
        await state.clear()
        return

    lines = ["👥 Введите <b>ID группы</b> для ученика:\n"]
    for g in groups:
        curator_name = g.get("curator_name") or "—"
        lines.append(f"[ID:{g['id']}] {g['title']} → {curator_name}")

    await state.update_data(tid=tid, auto_name=user["full_name"], username=user["username"])
    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(AddStudent.waiting_group_id)


@router.message(AddStudent.waiting_group_id)
async def adm_stu_group(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите ID группы.")
        return
    gid = int(text)
    group = await GroupRepo.get_by_id(gid)
    if not group:
        await message.answer("❌ Группа не найдена.")
        return
    await state.update_data(group_id=gid, curator_id=group["curator_id"], group_title=group["title"])
    data = await state.get_data()
    await message.answer(
        f"ФИО в базе: <b>{data['auto_name']}</b>\n"
        f"Введите <b>ФИО ученика</b> или отправьте <code>+</code> для использования текущего.",
        parse_mode="HTML"
    )
    await state.set_state(AddStudent.waiting_fullname)


@router.message(AddStudent.waiting_fullname)
async def adm_stu_name(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    text = (message.text or "").strip()
    fullname = data["auto_name"] if text == "+" else text

    if not fullname:
        await message.answer("⚠️ Введите ФИО или отправьте +")
        return

    tid = data["tid"]
    await StudentRepo.add(
        telegram_id=tid,
        username=data.get("username"),
        full_name=fullname,
        curator_id=data["curator_id"],
        group_id=data["group_id"]
    )
    await UserRepo.set_role(tid, "student")
    await UserRepo.set_access(tid, 1)
    await state.clear()

    # Найти куратора для уведомления
    curator = await CuratorRepo.get_by_id(data["curator_id"]) if data.get("curator_id") else None
    curator_name = curator["full_name"] if curator else "куратор"

    await message.answer(
        f"✅ Ученик добавлен: <b>{fullname}</b>\n"
        f"Группа: {data['group_title']}\n"
        f"ID: <code>{tid}</code>",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )
    # ── Уведомление ученику ────────────────────────────────────────────────
    try:
        await bot.send_message(
            tid,
            f"🎉 <b>Добро пожаловать!</b>\n\n"
            f"Вас добавил администратор в группу <b>{data['group_title']}</b>.\n"
            f"Ваш куратор: <b>{curator_name}</b>\n\n"
            f"Теперь вам доступно:\n"
            f"📚 Рабочие тетради\n"
            f"✅ Чек-листы\n"
            f"📤 Сдача РТ\n"
            f"🗓 Запись на зачёт\n\n"
            f"Нажмите /start чтобы открыть меню.",
            parse_mode="HTML"
        )
    except Exception as e:
        log.warning("Не удалось уведомить ученика %s: %s", tid, e)


@router.callback_query(F.data == "adm:stu:list")
async def adm_stu_list(callback: CallbackQuery) -> None:
    students = await StudentRepo.get_all()
    if not students:
        await callback.message.answer("📭 Учеников нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    # Разбить по страницам (по 20)
    lines = [f"👨‍🎓 <b>Ученики ({len(students)}):</b>\n"]
    for s in students[:50]:  # показываем первые 50
        group_title   = s.get("group_title") or "—"
        curator_name  = s.get("curator_name") or "—"
        lines.append(f"[ID:{s['id']}] {s['full_name']} | {group_title} | {curator_name}")

    if len(students) > 50:
        lines.append(f"\n... и ещё {len(students)-50} учеников.")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:stu:del")
async def adm_stu_del_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("🗑 Введите <b>ID ученика</b> (из списка) для удаления:", parse_mode="HTML")
    await state.set_state(DeleteStudent.waiting_student_id)
    await callback.answer()


@router.message(DeleteStudent.waiting_student_id)
async def adm_stu_del_do(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите ID ученика (число).")
        return
    sid = int(text)
    student = await StudentRepo.get_by_id(sid)
    if not student:
        await message.answer("❌ Ученик не найден.")
        await state.clear()
        return
    await StudentRepo.delete(sid)
    await UserRepo.set_role(student["telegram_id"], "user")
    await state.clear()
    await message.answer(
        f"✅ Ученик <b>{student['full_name']}</b> удалён.",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb()
    )


# ══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СДАЧ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:sub:list")
async def adm_sub_list(callback: CallbackQuery) -> None:
    subs = await SubmissionRepo.get_all(limit=50)
    if not subs:
        await callback.message.answer("📭 Сдач ещё нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    lines = [f"📥 <b>Последние сдачи ({len(subs)}):</b>\n"]
    for s in subs:
        try:
            dt = datetime.fromisoformat(s["submitted_at"])
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt_str = str(s["submitted_at"])
        group = s.get("group_title") or "—"
        curator = s.get("curator_name") or "—"
        lines.append(f"• {s['student_full_name']} | {group} | {dt_str}")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:sub:clear")
async def adm_sub_clear_confirm(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "⚠️ <b>Очистить список всех сдач РТ?</b>",
        parse_mode="HTML",
        reply_markup=confirm_clear_kb("sub_clear")
    )
    await callback.answer()


@router.callback_query(F.data == "confirm:sub_clear")
async def adm_sub_clear_do(callback: CallbackQuery) -> None:
    await SubmissionRepo.clear_all()
    await callback.message.edit_text("✅ Список сдач очищен.", reply_markup=back_to_admin_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ЭКСПОРТ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:exp:sub")
async def adm_exp_sub(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "📊 Выберите период для экспорта сдач:",
        reply_markup=export_filter_kb("sub")
    )
    await callback.answer()


@router.callback_query(F.data == "adm:exp:exam")
async def adm_exp_exam(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "📊 Выберите период для экспорта записей на зачёт:",
        reply_markup=export_filter_kb("exam")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exp:sub:"))
async def adm_exp_sub_do(callback: CallbackQuery, bot: Bot) -> None:
    period = callback.data.split(":")[2]
    await callback.message.answer("⏳ Генерирую Excel...")

    rows = await SubmissionRepo.get_filtered(period)
    if not rows:
        await callback.message.answer("📭 Нет данных за выбранный период.")
        await callback.answer()
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/tmp/submissions_{period}_{ts}.xlsx"
    await export_submissions(list(rows), out_path)

    await bot.send_document(
        callback.from_user.id,
        FSInputFile(out_path),
        caption=f"📊 Экспорт сдач РТ [{period}]\nСтрок: {len(rows)}"
    )
    Path(out_path).unlink(missing_ok=True)
    await callback.answer()


@router.callback_query(F.data.startswith("exp:exam:"))
async def adm_exp_exam_do(callback: CallbackQuery, bot: Bot) -> None:
    period = callback.data.split(":")[2]
    await callback.message.answer("⏳ Генерирую Excel...")

    rows = await ExamBookingRepo.get_all_for_export()
    if not rows:
        await callback.message.answer("📭 Нет данных о записях на зачёт.")
        await callback.answer()
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/tmp/exams_{ts}.xlsx"
    await export_exam_bookings(list(rows), out_path)

    await bot.send_document(
        callback.from_user.id,
        FSInputFile(out_path),
        caption=f"📊 Экспорт записей на зачёт\nСтрок: {len(rows)}"
    )
    Path(out_path).unlink(missing_ok=True)
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ОБЩИЙ CANCEL для confirm
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "confirm:cancel")
async def confirm_cancel(callback: CallbackQuery) -> None:
    await callback.message.edit_text("❌ Отменено.", reply_markup=back_to_admin_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ДОБАВИТЬ АДМИНИСТРАТОРА — по ID или @username (одиночно / до 15 разом)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("add_admin"))
async def add_admin_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👑 <b>Добавить администратора</b>\n\n"
        "Введите <b>Telegram ID</b> или <b>@username</b> пользователя.\n\n"
        "Можно добавить <b>до 15 человек сразу</b> — каждый с новой строки или через запятую:\n\n"
        "<code>@ivanov\n123456789\n@petrov</code>\n\n"
        "❗ Пользователь должен предварительно написать /start боту.\n"
        "Совет: попросите прислать свой ID через /myid",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(AddAdminFlex.waiting_identifiers)


@router.message(AddAdminFlex.waiting_identifiers, F.text == "❌ Отмена")
async def add_admin_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=back_to_admin_kb())


@router.message(AddAdminFlex.waiting_identifiers)
async def add_admin_do(message: Message, state: FSMContext, bot: Bot) -> None:
    identifiers = parse_identifiers(message.text or "")
    if not identifiers:
        await message.answer(
            "⚠️ Не найдено ни одного валидного ID или @username.\n\n"
            "Введите числовой ID (например <code>123456789</code>) "
            "или username (например <code>@ivanov</code>).",
            parse_mode="HTML"
        )
        return

    await state.clear()
    results = {"ok": [], "not_found": [], "already": []}

    for ident in identifiers:
        user = await UserRepo.resolve(ident)
        if not user:
            results["not_found"].append(ident)
            continue
        tid = user["telegram_id"]
        if user["role"] == "admin":
            results["already"].append(f"{ident} ({user['full_name']})")
            continue
        await UserRepo.set_role(tid, "admin")
        await UserRepo.set_access(tid, 1)
        results["ok"].append(f"{user['full_name']} ({ident})")
        try:
            await bot.send_message(
                tid,
                "👑 <b>Вам выданы права администратора!</b>\n\n"
                "Теперь вам доступна полная административная панель.\n"
                "Нажмите /start чтобы обновить меню.",
                parse_mode="HTML"
            )
        except Exception as e:
            log.warning("Не удалось уведомить нового админа %s: %s", tid, e)

    lines = ["👑 <b>Результат добавления администраторов:</b>\n"]
    if results["ok"]:
        lines.append(f"✅ Добавлено ({len(results['ok'])}):")
        lines += [f"  • {r}" for r in results["ok"]]
    if results["already"]:
        lines.append(f"\nℹ️ Уже были админами:")
        lines += [f"  • {r}" for r in results["already"]]
    if results["not_found"]:
        lines.append(f"\n❌ Не найдены в системе (нужно /start):")
        lines += [f"  • {r}" for r in results["not_found"]]

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())


# ══════════════════════════════════════════════════════════════════════════════
# ДОБАВИТЬ КУРАТОРА — flex (ID или @username) + массовое
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:cur:bulk")
async def adm_cur_bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "👨‍🏫 <b>Массовое добавление кураторов</b>\n\n"
        "Введите до <b>15 идентификаторов</b> — каждый с новой строки или через запятую.\n\n"
        "Принимаем:\n"
        "  • <code>@username</code>\n"
        "  • числовой <code>Telegram ID</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>@adilzhan\n"
        "123456789\n"
        "@zarina_k</code>\n\n"
        "❗ Все пользователи должны написать /start боту.\n"
        "Каждому придёт уведомление о назначении куратором.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(BulkAddCurators.waiting_identifiers)
    await callback.answer()


@router.message(BulkAddCurators.waiting_identifiers, F.text == "❌ Отмена")
async def bulk_curators_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=back_to_admin_kb())


@router.message(BulkAddCurators.waiting_identifiers)
async def bulk_curators_do(message: Message, state: FSMContext, bot: Bot) -> None:
    identifiers = parse_identifiers(message.text or "")
    if not identifiers:
        await message.answer(
            "⚠️ Нет валидных идентификаторов.\n"
            "Введите @username или числовой ID.",
            parse_mode="HTML"
        )
        return

    await state.clear()
    results = {"ok": [], "not_found": [], "already": []}

    for ident in identifiers:
        user = await UserRepo.resolve(ident)
        if not user:
            results["not_found"].append(ident)
            continue
        tid = user["telegram_id"]
        existing = await CuratorRepo.get_by_tid(tid)
        if existing:
            results["already"].append(f"{ident} ({user['full_name']})")
            continue
        await CuratorRepo.add(tid, user["username"], user["full_name"])
        await UserRepo.set_role(tid, "curator")
        await UserRepo.set_access(tid, 1)
        results["ok"].append(f"{user['full_name']} ({ident})")
        try:
            await bot.send_message(
                tid,
                "👨‍🏫 <b>Вы назначены куратором!</b>\n\n"
                "Вам открыты расширенные возможности:\n"
                "👥 Создание групп\n"
                "👨‍🎓 Добавление учеников\n"
                "📥 Просмотр сданных РТ\n"
                "🗓 Создание расписания зачётов\n\n"
                "Нажмите /start чтобы открыть меню куратора.",
                parse_mode="HTML"
            )
        except Exception as e:
            log.warning("Уведомление куратору %s не доставлено: %s", tid, e)

    lines = ["👨‍🏫 <b>Результат добавления кураторов:</b>\n"]
    if results["ok"]:
        lines.append(f"✅ Добавлено ({len(results['ok'])}):")
        lines += [f"  • {r}" for r in results["ok"]]
    if results["already"]:
        lines.append(f"\nℹ️ Уже были кураторами:")
        lines += [f"  • {r}" for r in results["already"]]
    if results["not_found"]:
        lines.append(f"\n❌ Не найдены в системе (нужно /start):")
        lines += [f"  • {r}" for r in results["not_found"]]

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())


# ══════════════════════════════════════════════════════════════════════════════
# МАССОВОЕ ДОБАВЛЕНИЕ УЧЕНИКОВ (администратором)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:stu:bulk")
async def adm_stu_bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    groups = await GroupRepo.get_all()
    if not groups:
        await callback.message.answer(
            "⚠️ Сначала создайте хотя бы одну группу.",
            reply_markup=back_to_admin_kb()
        )
        await callback.answer()
        return

    lines = ["👥 <b>Выберите группу</b> — введите её ID:\n"]
    for g in groups:
        curator_name = g.get("curator_name") or "—"
        lines.append(f"  <code>{g['id']}</code> — {g['title']} (куратор: {curator_name})")

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=cancel_kb())
    await state.set_state(BulkAddStudents.waiting_group_id)
    await callback.answer()


@router.message(BulkAddStudents.waiting_group_id, F.text == "❌ Отмена")
@router.message(BulkAddStudents.waiting_identifiers, F.text == "❌ Отмена")
async def bulk_students_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=back_to_admin_kb())


@router.message(BulkAddStudents.waiting_group_id)
async def adm_stu_bulk_group(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Введите числовой ID группы.")
        return
    gid   = int(text)
    group = await GroupRepo.get_by_id(gid)
    if not group:
        await message.answer("❌ Группа не найдена.")
        return

    await state.update_data(group_id=gid, group_title=group["title"],
                            curator_id=group["curator_id"])
    await message.answer(
        f"✅ Группа: <b>{group['title']}</b>\n\n"
        f"👨‍🎓 <b>Массовое добавление учеников</b>\n\n"
        f"Введите до <b>15 идентификаторов</b> — каждый с новой строки или через запятую:\n\n"
        f"Принимаем:\n"
        f"  • <code>@username</code>\n"
        f"  • числовой <code>Telegram ID</code>\n\n"
        f"<b>Пример:</b>\n"
        f"<code>@student1\n"
        f"987654321\n"
        f"@aisulu_k\n"
        f"111222333</code>\n\n"
        f"❗ Каждый ученик должен написать /start боту.\n"
        f"Каждому придёт уведомление о добавлении.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(BulkAddStudents.waiting_identifiers)


@router.message(BulkAddStudents.waiting_identifiers)
async def adm_stu_bulk_do(message: Message, state: FSMContext, bot: Bot) -> None:
    identifiers = parse_identifiers(message.text or "")
    if not identifiers:
        await message.answer(
            "⚠️ Нет валидных идентификаторов.\n"
            "Введите @username или числовой Telegram ID.",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    gid         = data["group_id"]
    group_title = data["group_title"]
    curator_id  = data["curator_id"]
    curator     = await CuratorRepo.get_by_id(curator_id) if curator_id else None
    curator_name = curator["full_name"] if curator else "—"
    await state.clear()

    results = {"ok": [], "not_found": [], "already": []}

    for ident in identifiers:
        user = await UserRepo.resolve(ident)
        if not user:
            results["not_found"].append(ident)
            continue
        tid = user["telegram_id"]
        existing = await StudentRepo.get_by_tid(tid)
        if existing:
            results["already"].append(f"{ident} ({user['full_name']})")
            continue
        await StudentRepo.add(tid, user["username"], user["full_name"], curator_id, gid)
        await UserRepo.set_role(tid, "student")
        await UserRepo.set_access(tid, 1)
        results["ok"].append(f"{user['full_name']} ({ident})")
        try:
            await bot.send_message(
                tid,
                f"🎉 <b>Добро пожаловать!</b>\n\n"
                f"Вас добавил администратор в группу <b>{group_title}</b>.\n"
                f"Куратор: <b>{curator_name}</b>\n\n"
                f"Теперь вам доступно:\n"
                f"📚 Рабочие тетради\n"
                f"✅ Чек-листы\n"
                f"📤 Сдача РТ\n"
                f"🗓 Запись на зачёт\n\n"
                f"Нажмите /start чтобы открыть меню.",
                parse_mode="HTML"
            )
        except Exception as e:
            log.warning("Уведомление ученику %s не доставлено: %s", tid, e)

    lines = [f"👨‍🎓 <b>Результат добавления в группу «{group_title}»:</b>\n"]
    if results["ok"]:
        lines.append(f"✅ Добавлено ({len(results['ok'])}):")
        lines += [f"  • {r}" for r in results["ok"]]
    if results["already"]:
        lines.append(f"\nℹ️ Уже в системе:")
        lines += [f"  • {r}" for r in results["already"]]
    if results["not_found"]:
        lines.append(f"\n❌ Не найдены (нужно /start):")
        lines += [f"  • {r}" for r in results["not_found"]]

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=back_to_admin_kb())


# ══════════════════════════════════════════════════════════════════════════════
# ПРАКТИКИ — просмотр, очистка, экспорт (только для админа)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:prac:list")
async def adm_prac_list(callback: CallbackQuery, bot: Bot) -> None:
    pracs = await PracticeRepo.get_all(limit=50)
    if not pracs:
        await callback.message.answer("📭 Практик ещё нет.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    lines = [f"📸 <b>Последние практики ({len(pracs)}):</b>\n"]
    for p in pracs:
        try:
            dt     = datetime.fromisoformat(p["submitted_at"])
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt_str = str(p["submitted_at"])
        desc    = f" · {p['description']}" if p.get("description") else ""
        curator = p.get("curator_name") or "—"
        lines.append(
            f"• <b>{p['student_full_name']}</b>{desc}\n"
            f"  👥 {p.get('group_title') or '—'}  |  👨‍🏫 {curator}  |  🕐 {dt_str}"
        )

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n<i>...показаны первые</i>"

    await callback.message.answer(text, parse_mode="HTML")

    # PDF-кнопки
    kb = InlineKeyboardBuilder()
    for p in pracs[:25]:
        try:
            dt_str = datetime.fromisoformat(p["submitted_at"]).strftime("%d.%m %H:%M")
        except Exception:
            dt_str = "—"
        name_s = p["student_full_name"].split()[0] if p["student_full_name"] else "?"
        desc_s = f" · {p['description'][:12]}" if p.get("description") else ""
        kb.button(text=f"📄 {name_s}{desc_s} · {dt_str}",
                  callback_data=f"adm_prac_pdf:{p['id']}")
    kb.button(text="◀️ Назад", callback_data="adm:back")
    kb.adjust(2, 1)
    await callback.message.answer("📄 <b>Скачать PDF практики:</b>",
                                  parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adm_prac_pdf:"))
async def adm_prac_get_pdf(callback: CallbackQuery) -> None:
    """Админ скачивает PDF практики — прямой поиск по ID."""
    try:
        prac_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    prac = await PracticeRepo.get_by_id(prac_id)
    if not prac:
        await callback.answer("❌ Практика не найдена.", show_alert=True)
        return

    pdf_path = Path(prac["pdf_path"])
    if not pdf_path.exists():
        log.warning("PDF практики не найден: %s", prac["pdf_path"])
        await callback.answer(f"⚠️ Файл не найден: {Path(prac['pdf_path']).name}", show_alert=True)
        return

    try:
        dt_str = datetime.fromisoformat(prac["submitted_at"]).strftime("%d.%m.%Y в %H:%M")
    except Exception:
        dt_str = str(prac["submitted_at"])

    try:
        desc_line   = f"\n📌 {prac['description']}" if prac["description"] else ""
        group_title  = prac["group_title"]  or "—"
        curator_name = prac["curator_name"] or "—"
    except Exception:
        desc_line    = ""
        group_title  = "—"
        curator_name = "—"

    await callback.message.answer_document(
        FSInputFile(pdf_path),
        caption=(
            f"📸 <b>Практика</b>\n\n"
            f"👤 {prac['student_full_name']}{desc_line}\n"
            f"📅 {dt_str}\n"
            f"👥 {group_title}  |  👨\u200d🏫 {curator_name}"
        ),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm:prac:clear")
async def adm_prac_clear_confirm(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "⚠️ <b>Удалить все практики учеников?</b>\n\nЭто действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=confirm_clear_kb("prac_clear")
    )
    await callback.answer()


@router.callback_query(F.data == "confirm:prac_clear")
async def adm_prac_clear_do(callback: CallbackQuery) -> None:
    await PracticeRepo.clear_all()
    await callback.message.edit_text("✅ Все практики удалены.", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:exp:prac")
async def adm_exp_prac(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "📊 Выберите период для экспорта практик:",
        reply_markup=export_filter_kb("prac")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exp:prac:"))
async def adm_exp_prac_do(callback: CallbackQuery, bot: Bot) -> None:
    period = callback.data.split(":")[2]
    await callback.message.answer("⏳ Генерирую Excel практик...")
    rows = await PracticeRepo.get_filtered(period)
    if not rows:
        await callback.message.answer("📭 Нет практик за выбранный период.")
        await callback.answer()
        return
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/tmp/practices_{period}_{ts}.xlsx"
    await export_practices(list(rows), out_path)
    await bot.send_document(
        callback.from_user.id,
        FSInputFile(out_path),
        caption=f"📊 Экспорт практик [{period}]\nСтрок: {len(rows)}"
    )
    Path(out_path).unlink(missing_ok=True)
    await callback.answer()
