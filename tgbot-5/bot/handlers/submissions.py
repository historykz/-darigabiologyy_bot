"""
handlers/submissions.py — Сдача РТ с подробными инструкциями на каждом шаге.
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, FSInputFile
from bot.config import TEMP_DIR, SUBMISSIONS_DIR
from bot.database import (
    UserRepo, StudentRepo, CuratorRepo,
    PhotoBufferRepo, SubmissionRepo, GroupRepo
)
# SubmissionRepo.get_by_student_id используется для «Мои сдачи»
from bot.services.pdf_service import photos_to_pdf
from bot.services.file_service import save_telegram_file
from bot.states import SubmitRT
from bot.keyboards import cancel_kb, submit_or_cancel_kb
from bot.utils.helpers import now_str, safe_filename

log = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📤 Сдать РТ")
async def submit_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id

    if not await UserRepo.has_access(uid):
        await message.answer(
            "⛔ <b>Доступ закрыт</b>\n\n"
            "У вас нет доступа к сдаче РТ.\n\n"
            "Для получения доступа:\n"
            "1. Введите /myid и скопируйте ваш ID\n"
            "2. Передайте куратору — он добавит вас в группу",
            parse_mode="HTML"
        )
        return

    await PhotoBufferRepo.clear(uid)

    await message.answer(
        "📤 <b>Сдача рабочей тетради</b>\n\n"
        "Сейчас вы отправите фото выполненной работы, "
        "бот соберёт их в один PDF и отправит вашему куратору.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Шаг 1 из 3 — Введите ФИО</b>\n\n"
        "Напишите своё полное ФИО — оно будет указано в PDF.\n\n"
        "📝 <b>Пример:</b> <code>Иванов Иван Иванович</code>\n\n"
        "❗ Введите имя точно как в журнале — куратор будет искать работу по нему.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(SubmitRT.waiting_fullname)


@router.message(SubmitRT.waiting_fullname, F.text == "❌ Отмена")
@router.message(SubmitRT.collecting_photos, F.text == "❌ Отменить")
async def submit_cancel(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    await PhotoBufferRepo.clear(uid)
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer(
        "❌ Сдача РТ отменена.\n\nВсе добавленные фото удалены.",
        reply_markup=await get_menu(uid)
    )


@router.message(SubmitRT.waiting_fullname)
async def submit_fullname(message: Message, state: FSMContext) -> None:
    fullname = (message.text or "").strip()

    if len(fullname) < 5 or not any(c.isalpha() for c in fullname):
        await message.answer(
            "⚠️ <b>Некорректное ФИО</b>\n\n"
            "Введите полное имя (минимум 5 символов).\n"
            "Пример: <code>Петрова Анна Сергеевна</code>",
            parse_mode="HTML"
        )
        return

    await state.update_data(fullname=fullname)
    await state.set_state(SubmitRT.collecting_photos)

    await message.answer(
        f"✅ ФИО принято: <b>{fullname}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Шаг 2 из 3 — Отправьте фото</b>\n\n"
        f"📸 Фотографируйте страницы и отправляйте их <b>по одному</b>.\n\n"
        f"<b>Советы для хорошего качества:</b>\n"
        f"• Хорошее освещение — не в темноте\n"
        f"• Держите телефон ровно над листом\n"
        f"• Весь текст должен быть виден и читаем\n"
        f"• Не обязательно делать фото идеально — главное чтобы куратор всё видел\n\n"
        f"После каждого фото бот покажет счётчик.\n"
        f"Когда все страницы отправлены — нажмите «📄 Отправить в PDF».",
        parse_mode="HTML",
        reply_markup=submit_or_cancel_kb()
    )


@router.message(SubmitRT.collecting_photos, F.photo)
async def submit_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    uid   = message.from_user.id
    photo = message.photo[-1]

    order = await PhotoBufferRepo.next_order(uid)
    filename = f"{uid}_{order}_{now_str()}.jpg"

    try:
        path = await save_telegram_file(bot, photo.file_id, str(TEMP_DIR), filename)
    except Exception as e:
        log.error("Ошибка сохранения фото: %s", e)
        await message.answer(
            "⚠️ <b>Не удалось сохранить фото.</b>\n\n"
            "Попробуйте отправить ещё раз. "
            "Если ошибка повторяется — обратитесь к куратору.",
            parse_mode="HTML"
        )
        return

    await PhotoBufferRepo.add(uid, path, order)
    count = await PhotoBufferRepo.count(uid)

    await message.answer(
        f"✅ <b>Фото #{count} добавлено</b>\n\n"
        f"Всего принято: <b>{count} {'страница' if count == 1 else 'страниц' if 2 <= count <= 4 else 'страниц'}</b>\n\n"
        f"{'📸 Отправьте следующее фото или нажмите кнопку ниже.' if count < 2 else f'📸 Продолжайте или нажмите «📄 Отправить в PDF» если все страницы готовы.'}",
        parse_mode="HTML",
        reply_markup=submit_or_cancel_kb()
    )


@router.message(SubmitRT.collecting_photos, F.text == "📄 Отправить в PDF")
async def submit_to_pdf(message: Message, state: FSMContext, bot: Bot) -> None:
    uid      = message.from_user.id
    data     = await state.get_data()
    fullname = data.get("fullname", "Неизвестно")
    photos   = await PhotoBufferRepo.get_by_student(uid)

    if not photos:
        await message.answer(
            "⚠️ <b>Фото не добавлены</b>\n\n"
            "Сначала отправьте хотя бы одно фото выполненной работы, "
            "затем нажмите «📄 Отправить в PDF».",
            parse_mode="HTML",
            reply_markup=submit_or_cancel_kb()
        )
        return

    await message.answer(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>Шаг 3 из 3 — Создаю PDF из {len(photos)} фото...</b>\n\n"
        f"Это займёт несколько секунд. Пожалуйста, подождите.",
        parse_mode="HTML"
    )

    photo_paths = [p["photo_path"] for p in photos]
    ts        = now_str()
    pdf_name  = f"{safe_filename(fullname)}_{ts}.pdf"
    pdf_path  = str(SUBMISSIONS_DIR / pdf_name)

    try:
        await photos_to_pdf(photo_paths, pdf_path)
    except Exception as e:
        log.error("Ошибка создания PDF: %s", e)
        await message.answer(
            "❌ <b>Ошибка при создании PDF.</b>\n\n"
            "Попробуйте снова или обратитесь к куратору.",
            parse_mode="HTML"
        )
        return

    student    = await StudentRepo.get_by_tid(uid)
    curator_id = student["curator_id"] if student else None
    group_id   = student["group_id"]   if student else None
    stu_db_id  = student["id"] if student else uid

    await SubmissionRepo.add(stu_db_id, curator_id, group_id, fullname, pdf_path)

    for p in photos:
        try: Path(p["photo_path"]).unlink(missing_ok=True)
        except Exception: pass
    await PhotoBufferRepo.clear(uid)
    await state.clear()

    from bot.handlers.user import get_menu
    kb = await get_menu(uid)

    await message.answer(
        f"🎉 <b>Рабочая тетрадь успешно сдана!</b>\n\n"
        f"👤 ФИО: {fullname}\n"
        f"📄 Страниц: {len(photos)}\n"
        f"📨 PDF отправлен куратору\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Куратор получил вашу работу и проверит её. "
        f"Если есть вопросы — он свяжется с вами.",
        parse_mode="HTML",
        reply_markup=kb
    )

    # PDF куратору
    if curator_id:
        curator = await CuratorRepo.get_by_id(curator_id)
        if curator:
            now         = datetime.now()
            uname       = message.from_user.username or "—"
            group_title = "—"
            if group_id:
                grp = await GroupRepo.get_by_id(group_id)
                if grp: group_title = grp["title"]

            caption = (
                f"📥 <b>Новая сданная РТ</b>\n\n"
                f"👨‍🎓 ФИО: {fullname}\n"
                f"Username: @{uname}\n"
                f"ID: <code>{uid}</code>\n"
                f"👥 Группа: {group_title}\n"
                f"📅 Дата: {now.strftime('%d.%m.%Y')}\n"
                f"🕐 Время: {now.strftime('%H:%M')}\n"
                f"📄 Страниц: {len(photos)}\n\n"
                f"📎 PDF прикреплён ниже."
            )
            try:
                await bot.send_document(curator["telegram_id"], FSInputFile(pdf_path),
                                        caption=caption, parse_mode="HTML")
            except Exception as e:
                log.error("Не удалось отправить PDF куратору %s: %s", curator["telegram_id"], e)


# Неожиданный тип сообщения во время сбора фото
@router.message(SubmitRT.collecting_photos)
async def submit_wrong_type(message: Message) -> None:
    await message.answer(
        "📸 <b>Нужно фото, а не текст</b>\n\n"
        "Отправляйте <b>фотографии</b> страниц рабочей тетради.\n"
        "Когда закончите — нажмите «📄 Отправить в PDF».\n\n"
        "Если хотите отменить — нажмите «❌ Отменить».",
        parse_mode="HTML",
        reply_markup=submit_or_cancel_kb()
    )


# ══════════════════════════════════════════════════════════════════════════════
# УЧЕНИК — МОИ СДАННЫЕ РТ
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📋 Мои сдачи")
async def my_submissions_student(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid     = message.from_user.id
    student = await StudentRepo.get_by_tid(uid)

    if not student:
        await message.answer(
            "⚠️ Вы не зарегистрированы как ученик.\n\n"
            "Обратитесь к куратору, чтобы вас добавили в систему."
        )
        return

    subs = await SubmissionRepo.get_by_student_id(student["id"])

    if not subs:
        await message.answer(
            "📭 <b>Вы ещё не сдавали рабочие тетради</b>\n\n"
            "Как только сдадите — здесь появится история с PDF-файлами.\n\n"
            "Чтобы сдать РТ — нажмите «📤 Сдать РТ» в главном меню.",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"📋 <b>Мои сданные РТ ({len(subs)} шт.)</b>\n\n"
        f"Ниже все ваши работы — нажмите на кнопку чтобы получить PDF.",
        parse_mode="HTML",
        reply_markup=_student_submissions_kb(subs)
    )


def _student_submissions_kb(subs):
    """Inline-кнопки — каждая сдача отдельной кнопкой с датой."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for s in subs:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(s["submitted_at"])
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            dt_str = str(s["submitted_at"])
        kb.button(
            text=f"📄 РТ · {dt_str}",
            callback_data=f"my_sub:{s['id']}"
        )
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("my_sub:"))
async def my_submission_get_pdf(callback: CallbackQuery) -> None:
    """Ученик запросил PDF своей сдачи."""
    sub_id  = int(callback.data.split(":")[1])
    uid     = callback.from_user.id
    student = await StudentRepo.get_by_tid(uid)

    if not student:
        await callback.answer("Ошибка.", show_alert=True)
        return

    # Найти сдачу (только свою!)
    subs = await SubmissionRepo.get_by_student_id(student["id"])
    sub  = next((s for s in subs if s["id"] == sub_id), None)

    if not sub:
        await callback.answer("Сдача не найдена.", show_alert=True)
        return

    pdf_path = Path(sub["pdf_path"])
    if not pdf_path.exists():
        await callback.answer(
            "⚠️ Файл не найден на сервере. Возможно был удалён при очистке.",
            show_alert=True
        )
        return

    try:
        from datetime import datetime
        dt     = datetime.fromisoformat(sub["submitted_at"])
        dt_str = dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        dt_str = str(sub["submitted_at"])

    await callback.message.answer_document(
        FSInputFile(pdf_path),
        caption=(
            f"📄 <b>Ваша сдача РТ</b>\n\n"
            f"👤 ФИО: {sub['student_full_name']}\n"
            f"📅 Дата: {dt_str}\n"
            f"👥 Группа: {sub.get('group_title') or '—'}\n"
            f"👨‍🏫 Куратор: {sub.get('curator_name') or '—'}\n\n"
            f"💡 Это ваш PDF — скачайте или перешлите при необходимости."
        ),
        parse_mode="HTML"
    )
    await callback.answer()
