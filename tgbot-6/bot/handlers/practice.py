"""
handlers/practice.py

📸 Скрин практики — ученик отправляет скрины выполненной практики,
бот собирает в PDF и отправляет куратору.

Функции:
  — ученик отправляет описание + скрины → PDF → куратору
  — «📸 Мои практики» — список с кнопками PDF
  — куратор видит все практики своих учеников с кнопками PDF
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import TEMP_DIR, SUBMISSIONS_DIR
from bot.database import (
    UserRepo, StudentRepo, CuratorRepo,
    GroupRepo, PracticeRepo, PracticePhotoRepo
)
from bot.services.pdf_service import photos_to_pdf
from bot.services.file_service import save_telegram_file
from bot.states import SubmitPractice
from bot.keyboards import cancel_kb, submit_or_cancel_kb
from bot.utils.helpers import now_str, safe_filename

log = logging.getLogger(__name__)
router = Router()


# ══════════════════════════════════════════════════════════════════════════════
# НАЧАЛО — «📸 Скрин практики»
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📸 Скрин практики")
async def practice_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id

    if not await UserRepo.has_access(uid):
        await message.answer(
            "⛔ <b>Доступ закрыт</b>\n\n"
            "Для отправки практики нужен доступ к системе.\n"
            "Введите /myid и передайте ID куратору.",
            parse_mode="HTML"
        )
        return

    await PracticePhotoRepo.clear(uid)

    await message.answer(
        "📸 <b>Отправить скрины практики</b>\n\n"
        "Здесь вы отправляете скриншоты выполненной практики.\n"
        "Бот соберёт их в PDF и пришлёт куратору на проверку.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Шаг 1 из 3 — Укажите тему практики</b>\n\n"
        "Напишите название или тему выполненной практики.\n\n"
        "📝 Примеры:\n"
        "  • <code>Биология — Тип простейших</code>\n"
        "  • <code>Химия — Органика тест</code>\n"
        "  • <code>Биология ЕНТ практика №3</code>\n\n"
        "Или отправьте <code>—</code> чтобы пропустить описание.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(SubmitPractice.waiting_description)


@router.message(SubmitPractice.waiting_description, F.text == "❌ Отмена")
@router.message(SubmitPractice.collecting_photos, F.text == "❌ Отменить")
async def practice_cancel(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    await PracticePhotoRepo.clear(uid)
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer(
        "❌ Отправка практики отменена.\nВсе добавленные скрины удалены.",
        reply_markup=await get_menu(uid)
    )


@router.message(SubmitPractice.waiting_description)
async def practice_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "—":
        desc = ""

    await state.update_data(description=desc)
    await state.set_state(SubmitPractice.collecting_photos)

    desc_line = f"\n📌 Тема: <b>{desc}</b>" if desc else ""
    await message.answer(
        f"✅ Тема принята.{desc_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Шаг 2 из 3 — Отправьте скрины</b>\n\n"
        f"📸 Отправляйте скриншоты по одному.\n\n"
        f"<b>Советы:</b>\n"
        f"• Скрин должен быть чётким и читаемым\n"
        f"• Весь текст должен быть виден полностью\n"
        f"• Если скринов несколько — отправляйте по порядку\n\n"
        f"После всех скринов нажмите «📄 Отправить в PDF».",
        parse_mode="HTML",
        reply_markup=submit_or_cancel_kb()
    )


# ══════════════════════════════════════════════════════════════════════════════
# ПРИЁМ СКРИНОВ
# ══════════════════════════════════════════════════════════════════════════════

@router.message(SubmitPractice.collecting_photos, F.photo)
async def practice_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    uid   = message.from_user.id
    photo = message.photo[-1]

    order    = await PracticePhotoRepo.next_order(uid)
    filename = f"prac_{uid}_{order}_{now_str()}.jpg"

    try:
        path = await save_telegram_file(bot, photo.file_id, str(TEMP_DIR), filename)
    except Exception as e:
        log.error("Ошибка сохранения скрина практики: %s", e)
        await message.answer(
            "⚠️ Не удалось сохранить скрин. Попробуйте ещё раз.",
            reply_markup=submit_or_cancel_kb()
        )
        return

    await PracticePhotoRepo.add(uid, path, order)
    count = await PracticePhotoRepo.count(uid)

    await message.answer(
        f"✅ <b>Скрин #{count} добавлен</b>\n\n"
        f"Всего скринов: <b>{count}</b>\n\n"
        f"Продолжайте или нажмите «📄 Отправить в PDF».",
        parse_mode="HTML",
        reply_markup=submit_or_cancel_kb()
    )


@router.message(SubmitPractice.collecting_photos)
async def practice_wrong_type(message: Message) -> None:
    await message.answer(
        "📸 <b>Нужен скриншот, а не текст</b>\n\n"
        "Отправляйте <b>скриншоты</b> выполненной практики.\n"
        "Когда все скрины готовы — нажмите «📄 Отправить в PDF».\n\n"
        "Чтобы отменить — нажмите «❌ Отменить».",
        parse_mode="HTML",
        reply_markup=submit_or_cancel_kb()
    )


# ══════════════════════════════════════════════════════════════════════════════
# ОТПРАВКА В PDF
# ══════════════════════════════════════════════════════════════════════════════

@router.message(SubmitPractice.collecting_photos, F.text == "📄 Отправить в PDF")
async def practice_to_pdf(message: Message, state: FSMContext, bot: Bot) -> None:
    uid    = message.from_user.id
    data   = await state.get_data()
    desc   = data.get("description", "")
    photos = await PracticePhotoRepo.get_by_student(uid)

    if not photos:
        await message.answer(
            "⚠️ <b>Скрины не добавлены</b>\n\n"
            "Сначала отправьте хотя бы один скриншот практики.",
            parse_mode="HTML",
            reply_markup=submit_or_cancel_kb()
        )
        return

    await message.answer(
        f"⏳ <b>Шаг 3 из 3 — Создаю PDF из {len(photos)} скринов...</b>\n\n"
        f"Пожалуйста, подождите несколько секунд.",
        parse_mode="HTML"
    )

    # Найти ученика
    student    = await StudentRepo.get_by_tid(uid)
    fullname   = student["full_name"] if student else (message.from_user.full_name or "Неизвестно")
    curator_id = student["curator_id"] if student else None
    group_id   = student["group_id"]   if student else None
    stu_db_id  = student["id"] if student else uid

    # Создать PDF
    photo_paths = [p["photo_path"] for p in photos]
    ts          = now_str()
    desc_part   = f"_{safe_filename(desc[:30])}" if desc else ""
    pdf_name    = f"practice_{safe_filename(fullname)}_{ts}{desc_part}.pdf"
    pdf_path    = str(SUBMISSIONS_DIR / pdf_name)

    try:
        await photos_to_pdf(photo_paths, pdf_path)
    except Exception as e:
        log.error("Ошибка создания PDF практики: %s", e)
        await message.answer("❌ Ошибка при создании PDF. Попробуйте снова.")
        return

    # Сохранить в БД
    await PracticeRepo.add(stu_db_id, curator_id, group_id, fullname, pdf_path, desc)

    # Очистить буфер
    for p in photos:
        try:
            Path(p["photo_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    await PracticePhotoRepo.clear(uid)
    await state.clear()

    from bot.handlers.user import get_menu
    kb = await get_menu(uid)

    desc_line = f"\n📌 Тема: {desc}" if desc else ""
    await message.answer(
        f"🎉 <b>Практика успешно отправлена!</b>\n\n"
        f"👤 ФИО: {fullname}{desc_line}\n"
        f"📄 Скринов: {len(photos)}\n"
        f"📨 PDF отправлен куратору на проверку\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Посмотреть свои практики: кнопка «📸 Мои практики»",
        parse_mode="HTML",
        reply_markup=kb
    )

    # Отправить PDF куратору
    if curator_id:
        curator = await CuratorRepo.get_by_id(curator_id)
        if curator:
            now         = datetime.now()
            uname       = message.from_user.username or "—"
            group_title = "—"
            if group_id:
                grp = await GroupRepo.get_by_id(group_id)
                if grp:
                    group_title = grp["title"]

            caption = (
                f"📸 <b>Новый скрин практики</b>\n\n"
                f"👨‍🎓 ФИО: {fullname}\n"
                f"Username: @{uname}\n"
                f"ID: <code>{uid}</code>\n"
                f"👥 Группа: {group_title}\n"
                f"📌 Тема: {desc or '—'}\n"
                f"📅 Дата: {now.strftime('%d.%m.%Y')}\n"
                f"🕐 Время: {now.strftime('%H:%M')}\n"
                f"📄 Скринов: {len(photos)}\n\n"
                f"📎 PDF прикреплён ниже."
            )
            try:
                await bot.send_document(
                    curator["telegram_id"],
                    FSInputFile(pdf_path),
                    caption=caption,
                    parse_mode="HTML"
                )
            except Exception as e:
                log.error("Не удалось отправить PDF практики куратору: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# «📸 МОИ ПРАКТИКИ» — ученик видит свои отправки с PDF
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📸 Мои практики")
async def my_practices(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid     = message.from_user.id
    student = await StudentRepo.get_by_tid(uid)

    if not student:
        await message.answer(
            "⚠️ Вы не зарегистрированы как ученик.\n\n"
            "Обратитесь к куратору — он добавит вас в систему.",
            parse_mode="HTML"
        )
        return

    practices = await PracticeRepo.get_by_student_id(student["id"])

    if not practices:
        await message.answer(
            "📭 <b>Вы ещё не отправляли практики</b>\n\n"
            "Как только отправите — здесь появится история с PDF-файлами.\n\n"
            "Чтобы отправить практику — нажмите «📸 Скрин практики».",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"📸 <b>Мои практики ({len(practices)} шт.)</b>\n\n"
        f"Нажмите на кнопку чтобы скачать PDF своей практики:",
        parse_mode="HTML",
        reply_markup=_practice_list_kb(practices, prefix="my_prac")
    )


@router.callback_query(F.data.startswith("my_prac:"))
async def my_practice_get_pdf(callback: CallbackQuery) -> None:
    prac_id = int(callback.data.split(":")[1])
    uid     = callback.from_user.id
    student = await StudentRepo.get_by_tid(uid)

    if not student:
        await callback.answer("Ошибка.", show_alert=True)
        return

    practices = await PracticeRepo.get_by_student_id(student["id"])
    prac      = next((p for p in practices if p["id"] == prac_id), None)

    if not prac:
        await callback.answer("Практика не найдена.", show_alert=True)
        return

    pdf_path = Path(prac["pdf_path"])
    if not pdf_path.exists():
        await callback.answer(
            "⚠️ Файл удалён с сервера.",
            show_alert=True
        )
        return

    try:
        dt     = datetime.fromisoformat(prac["submitted_at"])
        dt_str = dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        dt_str = str(prac["submitted_at"])

    desc_line = f"\n📌 Тема: {prac['description']}" if prac["description"] else ""

    await callback.message.answer_document(
        FSInputFile(pdf_path),
        caption=(
            f"📸 <b>Ваша практика</b>\n\n"
            f"📅 Дата: {dt_str}{desc_line}\n"
            f"👥 Группа: {prac.get('group_title') or '—'}\n"
            f"👨‍🏫 Куратор: {prac.get('curator_name') or '—'}"
        ),
        parse_mode="HTML"
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# КУРАТОР — список практик своих учеников с PDF
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📸 Практики учеников")
async def curator_practices(message: Message) -> None:
    uid     = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)

    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        return

    from bot.database import GroupRepo as GR
    groups = await GR.get_by_curator(curator["id"])
    total  = await PracticeRepo.get_by_curator(curator["id"], limit=1000)

    kb = InlineKeyboardBuilder()
    kb.button(text=f"📋 Все практики ({len(total)})",
              callback_data=f"prac_filter:all:{curator['id']}")
    for g in groups:
        cnt = len(await PracticeRepo.get_filtered("all", curator_id=curator["id"], group_id=g["id"]))
        kb.button(text=f"👥 {g['title']} ({cnt})",
                  callback_data=f"prac_filter:{g['id']}:{curator['id']}")
    kb.adjust(1)

    await message.answer(
        "📸 <b>Практики учеников</b>\n\n"
        "Выберите фильтр — «Все» или конкретную группу.\n"
        "После этого каждая практика показывается с кнопкой для скачивания PDF.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("prac_filter:"))
async def show_practices_filtered(callback: CallbackQuery) -> None:
    parts        = callback.data.split(":")
    group_filter = parts[1]
    curator_id   = int(parts[2])

    if group_filter == "all":
        pracs  = await PracticeRepo.get_by_curator(curator_id, limit=60)
        header = "📸 <b>Все практики</b>"
    else:
        pracs = await PracticeRepo.get_filtered("all", curator_id=curator_id,
                                                group_id=int(group_filter))
        from bot.database import GroupRepo as GR
        grp    = await GR.get_by_id(int(group_filter))
        header = f"📸 <b>Практики — {grp['title'] if grp else '?'}</b>"

    if not pracs:
        await callback.message.answer(
            "📭 Практик пока нет.\n\nКогда ученики отправят скрины — они появятся здесь."
        )
        await callback.answer()
        return

    # Текстовый список
    lines = [f"{header} ({len(pracs)} шт.)\n"]
    for i, p in enumerate(pracs, 1):
        try:
            dt     = datetime.fromisoformat(p["submitted_at"])
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt_str = str(p["submitted_at"])
        group_title = p["group_title"] if p["group_title"] else "—"
        desc_line   = f" · {p['description']}" if p["description"] else ""
        lines.append(
            f"<b>{i}. {p['student_full_name']}</b>{desc_line}\n"
            f"   👥 {group_title}  ·  🕐 {dt_str}"
        )

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n\n<i>...показаны первые записи</i>"
    await callback.message.answer(text, parse_mode="HTML")

    # PDF-кнопки
    if pracs:
        kb = InlineKeyboardBuilder()
        for p in pracs[:25]:
            try:
                dt     = datetime.fromisoformat(p["submitted_at"])
                dt_str = dt.strftime("%d.%m %H:%M")
            except Exception:
                dt_str = "—"
            name_short = p["student_full_name"].split()[0] if p["student_full_name"] else "?"
            desc_short = f" · {p['description'][:15]}" if p["description"] else ""
            kb.button(
                text=f"📄 {name_short}{desc_short} · {dt_str}",
                callback_data=f"get_prac_pdf:{p['id']}"
            )
        kb.adjust(2)
        await callback.message.answer(
            "📄 <b>Скачать PDF практики:</b>",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )

    await callback.answer()


@router.callback_query(F.data.startswith("get_prac_pdf:"))
async def get_practice_pdf(callback: CallbackQuery) -> None:
    """Куратор скачивает PDF конкретной практики."""
    prac_id = int(callback.data.split(":")[1])
    uid     = callback.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)

    if not curator:
        await callback.answer("Ошибка.", show_alert=True)
        return

    pracs = await PracticeRepo.get_by_curator(curator["id"], limit=1000)
    prac  = next((p for p in pracs if p["id"] == prac_id), None)

    if not prac:
        await callback.answer("Практика не найдена.", show_alert=True)
        return

    pdf_path = Path(prac["pdf_path"])
    if not pdf_path.exists():
        await callback.answer("⚠️ PDF не найден. Возможно был удалён.", show_alert=True)
        return

    try:
        dt     = datetime.fromisoformat(prac["submitted_at"])
        dt_str = dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        dt_str = str(prac["submitted_at"])

    desc_line = f"\n📌 Тема: {prac['description']}" if prac["description"] else ""

    await callback.message.answer_document(
        FSInputFile(pdf_path),
        caption=(
            f"📸 <b>Практика ученика</b>\n\n"
            f"👤 ФИО: {prac['student_full_name']}{desc_line}\n"
            f"📅 Дата: {dt_str}\n"
            f"👥 Группа: {prac.get('group_title') or '—'}"
        ),
        parse_mode="HTML"
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ — кнопки списка практик
# ══════════════════════════════════════════════════════════════════════════════

def _practice_list_kb(practices: list, prefix: str = "my_prac") -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for p in practices:
        try:
            dt     = datetime.fromisoformat(p["submitted_at"])
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt_str = str(p["submitted_at"])
        desc_part = f" · {p['description'][:20]}" if p.get("description") else ""
        kb.button(
            text=f"📄 {dt_str}{desc_part}",
            callback_data=f"{prefix}:{p['id']}"
        )
    kb.adjust(1)
    return kb.as_markup()
