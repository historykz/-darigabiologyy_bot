"""
handlers/curator.py

Полная панель куратора:
  — просмотр своих групп и учеников
  — создание групп
  — добавление / удаление учеников
  — просмотр сданных РТ с фильтром по группе
  — список записей на зачёт

Уведомления:
  — ученик получает сообщение при добавлении куратором
  — ученик получает сообщение при удалении из группы
"""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import (
    CuratorRepo, GroupRepo, StudentRepo,
    SubmissionRepo, ExamBookingRepo, UserRepo, PracticeRepo
)
from bot.filters.roles import IsCurator
from bot.keyboards import groups_list_kb, cancel_kb
from bot.services.exam_service import format_date_for_display
from bot.states import (
    CuratorAddGroup, CuratorAddStudent,
    CuratorDeleteStudent, CuratorDeleteGroup,
    AddStudentFlex, BulkAddStudents
)
from bot.utils.identifier import parse_identifiers

log = logging.getLogger(__name__)
router = Router()


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ — инлайн-кнопки управления группой
# ══════════════════════════════════════════════════════════════════════════════

def group_manage_kb(group_id: int) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить ученика", callback_data=f"cur_grp:add_stu:{group_id}")
    kb.button(text="🗑 Удалить ученика",  callback_data=f"cur_grp:del_stu:{group_id}")
    kb.button(text="🗑 Удалить группу",   callback_data=f"cur_grp:del:{group_id}")
    kb.button(text="◀️ К списку групп",   callback_data="cur_grp:back")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════════════════════
# МОИ ГРУППЫ — главный экран
# ══════════════════════════════════════════════════════════════════════════════

@router.message(IsCurator(), F.text == "👥 Мои группы")
async def my_groups(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        return

    groups = await GroupRepo.get_by_curator(curator["id"])

    # Кнопка «Создать группу» всегда есть
    kb = InlineKeyboardBuilder()
    for g in groups:
        cnt = len(await StudentRepo.get_by_group(g["id"]))
        kb.button(text=f"👥 {g['title']} ({cnt} уч.)", callback_data=f"grp:{g['id']}")
    kb.button(text="➕ Создать новую группу", callback_data="cur_grp:create")
    kb.adjust(1)

    if not groups:
        await message.answer(
            "📭 У вас пока нет групп.\nСоздайте первую группу:",
            reply_markup=kb.as_markup()
        )
    else:
        await message.answer(
            f"👥 <b>Ваши группы ({len(groups)}):</b>\n\n"
            "Нажмите на группу для управления:",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )


# ──────────────────────────────────────────────────────────────────────────────
# Нажали на группу → показать учеников + кнопки управления
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("grp:"))
async def show_group_detail(callback: CallbackQuery) -> None:
    group_id = int(callback.data.split(":")[1])
    group    = await GroupRepo.get_by_id(group_id)
    if not group:
        await callback.answer("Группа не найдена.", show_alert=True)
        return

    students = await StudentRepo.get_by_group(group_id)

    lines = [f"👥 <b>Группа: {group['title']}</b>\n"]
    if students:
        for i, s in enumerate(students, 1):
            uname = f"@{s['username']}" if s["username"] else "—"
            lines.append(f"{i}. {s['full_name']} ({uname})")
    else:
        lines.append("📭 Учеников пока нет.")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=group_manage_kb(group_id)
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# Вернуться к списку групп
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cur_grp:back")
async def back_to_groups(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator:
        await callback.answer("Ошибка.", show_alert=True)
        return
    groups = await GroupRepo.get_by_curator(curator["id"])
    kb = InlineKeyboardBuilder()
    for g in groups:
        cnt = len(await StudentRepo.get_by_group(g["id"]))
        kb.button(text=f"👥 {g['title']} ({cnt} уч.)", callback_data=f"grp:{g['id']}")
    kb.button(text="➕ Создать новую группу", callback_data="cur_grp:create")
    kb.adjust(1)
    await callback.message.answer(
        "👥 <b>Ваши группы:</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ ГРУППЫ куратором
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cur_grp:create")
async def create_group_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "📝 Введите <b>название новой группы</b>:\n"
        "Например: <code>Биология 11А</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(CuratorAddGroup.waiting_title)
    await callback.answer()


@router.message(CuratorAddGroup.waiting_title, F.text == "❌ Отмена")
async def create_group_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer("Отменено.", reply_markup=await get_menu(message.from_user.id))


@router.message(CuratorAddGroup.waiting_title)
async def create_group_done(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) < 2:
        await message.answer("⚠️ Введите название группы (минимум 2 символа).")
        return

    uid = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        await state.clear()
        return

    gid = await GroupRepo.add(title, curator["id"])
    await state.clear()

    from bot.handlers.user import get_menu
    await message.answer(
        f"✅ <b>Группа создана!</b>\n\n"
        f"👥 Название: <b>{title}</b>\n"
        f"🆔 ID группы: {gid}\n\n"
        f"Теперь вы можете добавить учеников через «👥 Мои группы».",
        parse_mode="HTML",
        reply_markup=await get_menu(uid)
    )


# ══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ГРУППЫ куратором
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("cur_grp:del:"))
async def delete_group_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    group_id = int(callback.data.split(":")[2])
    group    = await GroupRepo.get_by_id(group_id)
    if not group:
        await callback.answer("Группа не найдена.", show_alert=True)
        return

    students = await StudentRepo.get_by_group(group_id)
    warn = f"\n\n⚠️ В группе {len(students)} учеников — они потеряют привязку к группе." if students else ""

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"cur_grp:del_confirm:{group_id}")
    kb.button(text="❌ Отмена",      callback_data=f"grp:{group_id}")
    kb.adjust(2)

    await callback.message.answer(
        f"🗑 Удалить группу <b>{group['title']}</b>?{warn}",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cur_grp:del_confirm:"))
async def delete_group_do(callback: CallbackQuery) -> None:
    group_id = int(callback.data.split(":")[2])
    group    = await GroupRepo.get_by_id(group_id)
    if not group:
        await callback.answer("Группа уже удалена.", show_alert=True)
        return

    # Проверить что это группа этого куратора
    uid = callback.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator or group["curator_id"] != curator["id"]:
        await callback.answer("⛔ Это не ваша группа.", show_alert=True)
        return

    title = group["title"]
    await GroupRepo.delete(group_id)
    await callback.message.edit_text(f"✅ Группа <b>{title}</b> удалена.", parse_mode="HTML")
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ДОБАВЛЕНИЕ УЧЕНИКА куратором
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("cur_grp:add_stu:"))
async def add_student_start(callback: CallbackQuery, state: FSMContext) -> None:
    group_id = int(callback.data.split(":")[2])
    group    = await GroupRepo.get_by_id(group_id)
    if not group:
        await callback.answer("Группа не найдена.", show_alert=True)
        return

    await state.update_data(group_id=group_id, group_title=group["title"])
    await callback.message.answer(
        f"👨‍🎓 <b>Добавление учеников в группу «{group['title']}»</b>\n\n"
        f"Введите <b>до 15 человек</b> сразу — каждый с новой строки или через запятую.\n\n"
        f"Принимаем:\n"
        f"  • <code>@username</code>\n"
        f"  • числовой <code>Telegram ID</code>\n\n"
        f"<b>Пример:</b>\n"
        f"<code>@student1\n"
        f"987654321\n"
        f"@aisulu_k</code>\n\n"
        f"❗ Ученики должны предварительно написать /start боту.\n"
        f"Каждому придёт уведомление о добавлении.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(CuratorAddStudent.waiting_telegram_id)
    await callback.answer()


@router.message(CuratorAddStudent.waiting_telegram_id, F.text == "❌ Отмена")
@router.message(CuratorAddStudent.waiting_fullname, F.text == "❌ Отмена")
@router.message(CuratorAddStudent.waiting_group_id, F.text == "❌ Отмена")
async def add_student_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer("Отменено.", reply_markup=await get_menu(message.from_user.id))


@router.message(CuratorAddStudent.waiting_telegram_id)
async def add_student_tid(message: Message, state: FSMContext, bot: Bot) -> None:
    """
    Принимаем одного или сразу несколько учеников.
    Если один — идём дальше за ФИО.
    Если несколько — добавляем всех сразу.
    """
    identifiers = parse_identifiers(message.text or "")
    if not identifiers:
        await message.answer(
            "⚠️ Введите @username или числовой Telegram ID.\n"
            "Пример: <code>@student1</code> или <code>123456789</code>",
            parse_mode="HTML"
        )
        return

    data        = await state.get_data()
    gid         = data["group_id"]
    group_title = data["group_title"]
    uid         = message.from_user.id
    curator     = await CuratorRepo.get_by_tid(uid)

    # Если больше одного — массовое добавление без запроса ФИО
    if len(identifiers) > 1:
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
            await StudentRepo.add(tid, user["username"], user["full_name"],
                                  curator["id"] if curator else None, gid)
            await UserRepo.set_role(tid, "student")
            await UserRepo.set_access(tid, 1)
            results["ok"].append(f"{user['full_name']} ({ident})")
            try:
                await bot.send_message(
                    tid,
                    f"🎉 <b>Добро пожаловать!</b>\n\n"
                    f"Вас добавил куратор <b>{curator['full_name'] if curator else '—'}</b> "
                    f"в группу <b>{group_title}</b>.\n\n"
                    f"Теперь вам доступно:\n"
                    f"📚 Рабочие тетради\n"
                    f"✅ Чек-листы\n"
                    f"📤 Сдача РТ\n"
                    f"🗓 Запись на зачёт\n\n"
                    f"Нажмите /start чтобы открыть меню.",
                    parse_mode="HTML"
                )
            except Exception as e:
                log.warning("Уведомление ученику %s: %s", tid, e)

        from bot.handlers.user import get_menu
        lines = [f"👨‍🎓 <b>Результат добавления в «{group_title}»:</b>\n"]
        if results["ok"]:
            lines.append(f"✅ Добавлено ({len(results['ok'])}):")
            lines += [f"  • {r}" for r in results["ok"]]
        if results["already"]:
            lines.append(f"\nℹ️ Уже в системе:")
            lines += [f"  • {r}" for r in results["already"]]
        if results["not_found"]:
            lines.append(f"\n❌ Не найдены (нужно /start):")
            lines += [f"  • {r}" for r in results["not_found"]]
        await message.answer("\n".join(lines), parse_mode="HTML",
                             reply_markup=await get_menu(uid))
        return

    # Один ученик — спросить ФИО
    ident = identifiers[0]
    user  = await UserRepo.resolve(ident)
    if not user:
        await message.answer(
            f"❌ Пользователь <code>{ident}</code> не найден в системе.\n\n"
            f"Попросите ученика написать /start боту, затем попробуйте снова.",
            parse_mode="HTML"
        )
        return

    tid = user["telegram_id"]
    existing = await StudentRepo.get_by_tid(tid)
    if existing:
        grp = await GroupRepo.get_by_id(existing["group_id"]) if existing["group_id"] else None
        grp_name = grp["title"] if grp else "другой группе"
        await message.answer(
            f"⚠️ Этот пользователь уже является учеником в <b>{grp_name}</b>.\n\n"
            f"Если нужно перевести — сначала удалите его из той группы.",
            parse_mode="HTML"
        )
        return

    await state.update_data(tid=tid, auto_name=user["full_name"], username=user["username"])
    await message.answer(
        f"Пользователь найден: <b>{user['full_name']}</b>\n"
        f"(@{user['username'] or '—'} | ID: <code>{tid}</code>)\n\n"
        f"Введите <b>полное ФИО</b> или отправьте <code>+</code> чтобы оставить это имя.",
        parse_mode="HTML"
    )
    await state.set_state(CuratorAddStudent.waiting_fullname)


@router.message(CuratorAddStudent.waiting_fullname)
async def add_student_name(message: Message, state: FSMContext, bot: Bot) -> None:
    data     = await state.get_data()
    text     = (message.text or "").strip()
    fullname = data["auto_name"] if text == "+" else text

    if not fullname or len(fullname) < 3:
        await message.answer("⚠️ Введите ФИО (минимум 3 символа) или отправьте +")
        return

    tid        = data["tid"]
    group_id   = data["group_id"]
    group_title = data["group_title"]
    uid        = message.from_user.id
    curator    = await CuratorRepo.get_by_tid(uid)

    await StudentRepo.add(
        telegram_id=tid,
        username=data.get("username"),
        full_name=fullname,
        curator_id=curator["id"],
        group_id=group_id
    )
    await UserRepo.set_role(tid, "student")
    await UserRepo.set_access(tid, 1)
    await state.clear()

    from bot.handlers.user import get_menu
    await message.answer(
        f"✅ <b>Ученик добавлен!</b>\n\n"
        f"👨‍🎓 ФИО: {fullname}\n"
        f"👥 Группа: {group_title}\n"
        f"🆔 Telegram ID: <code>{tid}</code>",
        parse_mode="HTML",
        reply_markup=await get_menu(uid)
    )

    # ── Уведомление ученику ──────────────────────────────────────────────────
    try:
        await bot.send_message(
            tid,
            f"🎉 <b>Добро пожаловать!</b>\n\n"
            f"Вас добавил куратор <b>{curator['full_name']}</b> "
            f"в группу <b>{group_title}</b>.\n\n"
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
        await message.answer(
            f"⚠️ Ученик добавлен, но уведомление не доставлено "
            f"(возможно, он не запустил бота)."
        )


# ══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ УЧЕНИКА куратором
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("cur_grp:del_stu:"))
async def delete_student_from_group(callback: CallbackQuery, state: FSMContext) -> None:
    group_id = int(callback.data.split(":")[2])
    group    = await GroupRepo.get_by_id(group_id)
    students = await StudentRepo.get_by_group(group_id)

    if not students:
        await callback.answer("В этой группе нет учеников.", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    for s in students:
        kb.button(
            text=f"🗑 {s['full_name']}",
            callback_data=f"cur_del_stu:{s['id']}:{group_id}"
        )
    kb.button(text="❌ Отмена", callback_data=f"grp:{group_id}")
    kb.adjust(1)

    await callback.message.answer(
        f"Выберите ученика для удаления из группы <b>{group['title']}</b>:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cur_del_stu:"))
async def delete_student_confirm(callback: CallbackQuery, bot: Bot) -> None:
    parts      = callback.data.split(":")
    student_id = int(parts[1])
    group_id   = int(parts[2])

    # Проверить что это ученик этого куратора
    uid     = callback.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    student = await StudentRepo.get_by_id(student_id)

    if not student or not curator or student["curator_id"] != curator["id"]:
        await callback.answer("⛔ Этот ученик не в вашей группе.", show_alert=True)
        return

    fullname = student["full_name"]
    tid      = student["telegram_id"]

    await StudentRepo.delete(student_id)
    await UserRepo.set_role(tid, "user")
    await UserRepo.set_access(tid, 0)

    await callback.message.edit_text(
        f"✅ Ученик <b>{fullname}</b> удалён из группы.",
        parse_mode="HTML"
    )
    await callback.answer()

    # ── Уведомление удалённому ученику ───────────────────────────────────────
    try:
        await bot.send_message(
            tid,
            f"ℹ️ Вас удалил из группы куратор <b>{curator['full_name']}</b>.\n\n"
            f"Доступ к материалам приостановлен.\n"
            f"По вопросам обращайтесь к куратору.",
            parse_mode="HTML"
        )
    except Exception as e:
        log.warning("Не удалось уведомить удалённого ученика %s: %s", tid, e)


# ══════════════════════════════════════════════════════════════════════════════
# СДАННЫЕ РТ — список с фильтром по группе
# ══════════════════════════════════════════════════════════════════════════════

@router.message(IsCurator(), F.text == "📥 Сданные РТ")
async def my_submissions(message: Message) -> None:
    uid     = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        return

    groups = await GroupRepo.get_by_curator(curator["id"])
    total  = await SubmissionRepo.get_by_curator(curator["id"], limit=1000)

    # Inline-кнопки: Все + по каждой группе
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📋 Все сдачи ({len(total)})", callback_data=f"sub_filter:all:{curator['id']}")
    for g in groups:
        from bot.database import SubmissionRepo as SR
        cnt = len(await SR.get_filtered("all", curator_id=curator["id"], group_id=g["id"]))
        kb.button(text=f"👥 {g['title']} ({cnt})", callback_data=f"sub_filter:{g['id']}:{curator['id']}")
    kb.adjust(1)

    await message.answer(
        "📥 <b>Сданные РТ</b>\n\n"
        "Выберите фильтр — нажмите «Все сдачи» или конкретную группу.\n"
        "После этого каждая сдача будет показана с кнопкой для скачивания PDF.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("sub_filter:"))
async def show_submissions_filtered(callback: CallbackQuery) -> None:
    parts        = callback.data.split(":")
    group_filter = parts[1]
    curator_id   = int(parts[2])

    if group_filter == "all":
        subs   = await SubmissionRepo.get_by_curator(curator_id, limit=60)
        header = "📥 <b>Все сданные РТ</b>"
    else:
        subs = await SubmissionRepo.get_filtered("all", curator_id=curator_id, group_id=int(group_filter))
        grp  = await GroupRepo.get_by_id(int(group_filter))
        header = f"📥 <b>Сданные РТ — {grp['title'] if grp else '?'}</b>"

    if not subs:
        await callback.message.answer(
            "📭 Сдач пока нет.\n\n"
            "Как только ученики сдадут РТ — они появятся здесь."
        )
        await callback.answer()
        return

    # Сначала отправляем текстовый список
    lines = [f"{header} ({len(subs)} шт.)\n"]
    for i, s in enumerate(subs, 1):
        try:
            dt = datetime.fromisoformat(s["submitted_at"])
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt_str = str(s["submitted_at"])
        group_title = s["group_title"] if s["group_title"] else "—"
        lines.append(
            f"<b>{i}. {s['student_full_name']}</b>\n"
            f"   👥 {group_title}  ·  🕐 {dt_str}"
        )

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n\n<i>...показаны первые записи. Используйте фильтр по группе.</i>"

    await callback.message.answer(text, parse_mode="HTML")

    # Затем inline-кнопки для скачивания PDF каждой сдачи
    kb = InlineKeyboardBuilder()
    for s in subs[:25]:  # Telegram ограничивает кол-во кнопок
        try:
            dt = datetime.fromisoformat(s["submitted_at"])
            dt_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            dt_str = "—"
        # Короткое имя для кнопки
        name_short = s["student_full_name"].split()[0] if s["student_full_name"] else "?"
        kb.button(
            text=f"📄 {name_short} · {dt_str}",
            callback_data=f"get_sub_pdf:{s['id']}"
        )
    kb.adjust(2)

    await callback.message.answer(
        "📄 <b>Скачать PDF</b> — нажмите кнопку нужной сдачи:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("get_sub_pdf:"))
async def get_sub_pdf(callback: CallbackQuery) -> None:
    """Куратор скачивает PDF конкретной сдачи — прямой поиск по ID."""
    try:
        sub_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    uid = callback.from_user.id

    # Получаем сдачу напрямую по ID — быстро и без лишних запросов
    sub = await SubmissionRepo.get_by_id(sub_id)

    if not sub:
        await callback.answer("❌ Сдача не найдена в базе.", show_alert=True)
        return

    # Проверяем доступ: сдача должна принадлежать куратору ИЛИ пользователь — админ
    from bot.database import UserRepo as UR
    role = await UR.get_role(uid)
    if role != "admin":
        curator = await CuratorRepo.get_by_tid(uid)
        if not curator or sub["curator_id"] != curator["id"]:
            await callback.answer("⛔ У вас нет доступа к этой сдаче.", show_alert=True)
            return

    # Проверяем файл
    from pathlib import Path as _Path
    pdf_path = _Path(sub["pdf_path"])

    if not pdf_path.exists():
        log.warning("PDF не найден: %s", sub["pdf_path"])
        await callback.answer(
            f"⚠️ Файл не найден на сервере.\nПуть: {pdf_path.name}",
            show_alert=True
        )
        return

    try:
        dt     = datetime.fromisoformat(sub["submitted_at"])
        dt_str = dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        dt_str = str(sub["submitted_at"])

    try:
        group_title = sub["group_title"] or "—"
    except Exception:
        group_title = "—"

    await callback.message.answer_document(
        FSInputFile(pdf_path),
        caption=(
            f"📄 <b>Сдача РТ</b>\n\n"
            f"👤 ФИО: {sub['student_full_name']}\n"
            f"📅 Дата: {dt_str}\n"
            f"👥 Группа: {group_title}"
        ),
        parse_mode="HTML"
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# СПИСОК УЧЕНИКОВ куратора (быстрый доступ)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(IsCurator(), F.text == "👨‍🎓 Мои ученики")
async def my_students(message: Message) -> None:
    uid = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        return

    students = await StudentRepo.get_by_curator(curator["id"])
    if not students:
        await message.answer(
            "📭 У вас пока нет учеников.\n"
            "Добавьте их через «👥 Мои группы» → выберите группу → «➕ Добавить ученика»."
        )
        return

    lines = [f"👨‍🎓 <b>Ваши ученики ({len(students)}):</b>\n"]
    for i, s in enumerate(students, 1):
        uname = f"@{s['username']}" if s["username"] else "—"
        # Получить название группы
        grp_title = "—"
        if s["group_id"]:
            grp = await GroupRepo.get_by_id(s["group_id"])
            if grp:
                grp_title = grp["title"]
        lines.append(f"{i}. <b>{s['full_name']}</b> ({uname})\n   👥 {grp_title}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# ЗАПИСИ НА ЗАЧЁТ куратора
# ══════════════════════════════════════════════════════════════════════════════

@router.message(IsCurator(), F.text == "📋 Мои записи на зачёт")
async def my_exam_bookings(message: Message) -> None:
    uid     = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)
    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        return

    bookings = await ExamBookingRepo.get_by_curator(curator["id"])
    if not bookings:
        await message.answer("📭 Нет активных записей на зачёт.")
        return

    lines = [f"🗓 <b>Записи на зачёт ({len(bookings)})</b>\n"]
    for i, b in enumerate(bookings, 1):
        display_date = format_date_for_display(b["slot_date"])
        lines.append(
            f"{i}. <b>{b['student_full_name']}</b>\n"
            f"   📅 {display_date}  🕐 {b['slot_time']}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")
