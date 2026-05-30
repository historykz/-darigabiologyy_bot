"""
handlers/exams.py

Запись на зачёт:
  — ученик выбирает ДЕНЬ из всех доступных дат,
    потом выбирает конкретный слот в этот день
  — поддержка нескольких дней
  — куратор создаёт слоты, может добавлять разные даты
  — отмена записи если > 1 часа
  — подробные объяснения на каждом шаге
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.database import (
    ExamSlotRepo, ExamBookingRepo,
    CuratorRepo, StudentRepo, GroupRepo
)
from bot.services.exam_service import (
    generate_slots, validate_date,
    format_date_for_db, format_date_for_display
)
from bot.states import CreateExamSlots
from bot.keyboards import cancel_kb

log = logging.getLogger(__name__)
router = Router()


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════════════════════

def dates_keyboard(dates: list[str]) -> InlineKeyboardBuilder:
    """Кнопки выбора даты."""
    kb = InlineKeyboardBuilder()
    for d in dates:
        display = format_date_for_display(d)
        kb.button(text=f"📅 {display}", callback_data=f"exam_date:{d}")
    kb.button(text="❌ Отмена", callback_data="exam_date:cancel")
    kb.adjust(1)
    return kb.as_markup()


def slots_keyboard(slots: list, back_date: str) -> InlineKeyboardBuilder:
    """Кнопки конкретных слотов на выбранную дату."""
    kb = InlineKeyboardBuilder()
    for s in slots:
        kb.button(text=f"🕐 {s['slot_time']}  ({s['duration_minutes']} мин)",
                  callback_data=f"book:{s['id']}")
    kb.button(text="◀️ Выбрать другой день", callback_data=f"exam_back_dates")
    kb.button(text="❌ Отмена",               callback_data="exam_date:cancel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def cancel_booking_keyboard(booking_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить запись", callback_data=f"cancel_booking:{booking_id}")
    kb.button(text="🔗 Открыть Meet",   callback_data=f"open_meet:{booking_id}")
    kb.adjust(1)
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════════════════════
# УЧЕНИК — ЗАПИСЬ НА ЗАЧЁТ
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🗓 Запись на зачёт")
async def exam_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid     = message.from_user.id
    student = await StudentRepo.get_by_tid(uid)

    # Если куратор — показать его меню
    curator = await CuratorRepo.get_by_tid(uid)
    if curator:
        await show_curator_exam_info(message, curator)
        return

    if not student:
        await message.answer(
            "⚠️ <b>Вы не зарегистрированы как ученик</b>\n\n"
            "Чтобы записаться на зачёт, нужно быть добавленным в группу.\n\n"
            "<b>Что сделать:</b>\n"
            "1. Введите /myid — скопируйте ваш Telegram ID\n"
            "2. Передайте куратору — он добавит вас в систему",
            parse_mode="HTML"
        )
        return

    # Проверить активную запись
    existing = await ExamBookingRepo.get_active_by_student(student["id"])
    if existing:
        display_date = format_date_for_display(existing["slot_date"])
        meet         = existing.get("google_meet_link") or "—"
        slot_dt      = datetime.fromisoformat(f"{existing['slot_date']} {existing['slot_time']}")
        delta_h      = (slot_dt - datetime.now()).total_seconds() / 3600

        can_cancel = delta_h > 1
        kb = InlineKeyboardBuilder()
        if meet and meet != "—":
            kb.button(text="🔗 Открыть Google Meet", callback_data=f"open_meet:{existing['id']}")
        if can_cancel:
            kb.button(text="❌ Отменить запись", callback_data=f"cancel_booking:{existing['id']}")
        kb.adjust(1)

        cancel_note = (
            f"\n\n❌ <b>Отменить запись:</b> доступно пока до зачёта больше 1 часа."
            if can_cancel else
            f"\n\n🔒 Отменить запись нельзя — до зачёта меньше 1 часа."
        )

        await message.answer(
            f"📋 <b>У вас уже есть запись на зачёт</b>\n\n"
            f"📅 Дата: <b>{display_date}</b>\n"
            f"🕐 Время: <b>{existing['slot_time']}</b>\n"
            f"👨‍🏫 Куратор: <b>{existing['curator_name']}</b>\n"
            f"🔗 Google Meet: {meet}\n\n"
            f"⏰ <b>Напоминания:</b>\n"
            f"• За 10 минут до начала придёт уведомление\n"
            f"• В момент начала придёт ссылка на Meet"
            f"{cancel_note}",
            parse_mode="HTML",
            reply_markup=kb.as_markup() if kb.buttons else None
        )
        return

    # Нет записи — показать доступные даты
    curator_id = student["curator_id"]
    if not curator_id:
        await message.answer(
            "⚠️ <b>Куратор не назначен</b>\n\n"
            "Обратитесь к администратору, чтобы вам назначили куратора.",
            parse_mode="HTML"
        )
        return

    dates = await ExamSlotRepo.get_free_dates_by_curator(curator_id)
    if not dates:
        await message.answer(
            "📭 <b>Нет доступных слотов для записи</b>\n\n"
            "Ваш куратор ещё не создал расписание зачётов.\n\n"
            "Что делать:\n"
            "• Обратитесь к куратору и попросите создать расписание\n"
            "• Проверьте позже — когда куратор добавит даты, они появятся здесь",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"🗓 <b>Запись на зачёт</b>\n\n"
        f"Доступно <b>{len(dates)} {'день' if len(dates)==1 else 'дня' if len(dates)<5 else 'дней'}</b> для записи.\n\n"
        f"<b>Шаг 1 из 2 — Выберите удобный день:</b>\n\n"
        f"💡 После выбора дня вы увидите все свободные временны́е слоты.",
        parse_mode="HTML",
        reply_markup=dates_keyboard(dates)
    )
    # Сохраним curator_id для следующего шага
    await state.update_data(curator_id=curator_id, student_id=student["id"],
                            student_full_name=student["full_name"],
                            group_id=student["group_id"])


# ──────────────────────────────────────────────────────────────────────────────
# Ученик выбрал дату → показать слоты этого дня
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("exam_date:"))
async def exam_choose_date(callback: CallbackQuery, state: FSMContext) -> None:
    date_str = callback.data.split(":", 1)[1]

    if date_str == "cancel":
        await callback.message.edit_text("❌ Запись на зачёт отменена.")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    curator_id = data.get("curator_id")

    if not curator_id:
        # Получим куратора заново
        uid     = callback.from_user.id
        student = await StudentRepo.get_by_tid(uid)
        if not student or not student["curator_id"]:
            await callback.answer("Ошибка: куратор не найден.", show_alert=True)
            return
        curator_id = student["curator_id"]
        await state.update_data(curator_id=curator_id, student_id=student["id"],
                                student_full_name=student["full_name"],
                                group_id=student["group_id"])

    slots = await ExamSlotRepo.get_free_by_curator_and_date(curator_id, date_str)
    if not slots:
        await callback.answer("На эту дату нет свободных слотов.", show_alert=True)
        return

    display_date = format_date_for_display(date_str)
    await state.update_data(selected_date=date_str)

    await callback.message.edit_text(
        f"📅 <b>Дата: {display_date}</b>\n\n"
        f"Доступно слотов: <b>{len(slots)}</b>\n\n"
        f"<b>Шаг 2 из 2 — Выберите удобное время:</b>\n\n"
        f"💡 Каждый слот — отдельное время зачёта.\n"
        f"После выбора бот подтвердит запись и пришлёт ссылку Google Meet.",
        parse_mode="HTML",
        reply_markup=slots_keyboard(slots, date_str)
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# Назад к выбору дат
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "exam_back_dates")
async def exam_back_to_dates(callback: CallbackQuery, state: FSMContext) -> None:
    data       = await state.get_data()
    curator_id = data.get("curator_id")

    if not curator_id:
        uid     = callback.from_user.id
        student = await StudentRepo.get_by_tid(uid)
        if not student or not student["curator_id"]:
            await callback.answer("Ошибка.", show_alert=True)
            return
        curator_id = student["curator_id"]

    dates = await ExamSlotRepo.get_free_dates_by_curator(curator_id)
    if not dates:
        await callback.message.edit_text("📭 Больше нет доступных дат.")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"🗓 <b>Выберите удобный день</b> ({len(dates)} доступно):",
        parse_mode="HTML",
        reply_markup=dates_keyboard(dates)
    )
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# Ученик выбрал конкретный слот → бронируем
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("book:"))
async def book_slot(callback: CallbackQuery, state: FSMContext) -> None:
    slot_key = callback.data.split(":", 1)[1]

    if slot_key == "cancel":
        await callback.message.edit_text("❌ Запись на зачёт отменена.")
        await state.clear()
        await callback.answer()
        return

    slot_id = int(slot_key)
    uid     = callback.from_user.id
    student = await StudentRepo.get_by_tid(uid)

    if not student:
        await callback.answer("Вы не зарегистрированы как ученик.", show_alert=True)
        return

    slot = await ExamSlotRepo.get_by_id(slot_id)
    if not slot or slot["is_booked"]:
        await callback.answer(
            "⚠️ Этот слот уже занят. Выберите другое время.",
            show_alert=True
        )
        return

    # Нет ли уже активной записи
    existing = await ExamBookingRepo.get_active_by_student(student["id"])
    if existing:
        await callback.answer(
            "У вас уже есть активная запись на зачёт. "
            "Сначала отмените её.", show_alert=True
        )
        return

    meet_link  = slot["google_meet_link"] or ""
    booking_dt = f"{slot['slot_date']} {slot['slot_time']}"

    await ExamSlotRepo.book(slot_id, student["id"])
    booking_id = await ExamBookingRepo.add(
        slot_id=slot_id,
        student_id=student["id"],
        curator_id=slot["curator_id"],
        group_id=student["group_id"],
        student_full_name=student["full_name"],
        booking_datetime=booking_dt,
        meet_link=meet_link
    )

    curator      = await CuratorRepo.get_by_id(slot["curator_id"])
    curator_name = curator["full_name"] if curator else "—"
    display_date = format_date_for_display(slot["slot_date"])

    await state.clear()

    meet_text = (
        f"🔗 Google Meet: <a href='{meet_link}'>{meet_link}</a>"
        if meet_link else
        "🔗 Google Meet: куратор пришлёт ссылку позже"
    )

    kb = InlineKeyboardBuilder()
    if meet_link:
        kb.button(text="🔗 Открыть Google Meet", callback_data=f"open_meet:{booking_id}")
    kb.button(text="❌ Отменить запись", callback_data=f"cancel_booking:{booking_id}")
    kb.adjust(1)

    await callback.message.edit_text(
        f"✅ <b>Вы записались на зачёт!</b>\n\n"
        f"📅 Дата: <b>{display_date}</b>\n"
        f"🕐 Время: <b>{slot['slot_time']}</b>\n"
        f"⏱ Длительность: {slot['duration_minutes']} мин\n"
        f"👨‍🏫 Куратор: <b>{curator_name}</b>\n"
        f"{meet_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ <b>Напоминания придут автоматически:</b>\n"
        f"• За 10 минут до начала\n"
        f"• В момент начала — со ссылкой Meet\n\n"
        f"❌ Отменить запись можно если до зачёта больше 1 часа.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await callback.answer("✅ Запись подтверждена!")

    # Уведомить куратора
    if curator:
        try:
            uname       = callback.from_user.username or "—"
            group_title = "—"
            if student["group_id"]:
                grp = await GroupRepo.get_by_id(student["group_id"])
                if grp: group_title = grp["title"]

            await callback.bot.send_message(
                curator["telegram_id"],
                f"🗓 <b>Новая запись на зачёт</b>\n\n"
                f"👨‍🎓 ФИО: {student['full_name']}\n"
                f"Username: @{uname}\n"
                f"👥 Группа: {group_title}\n"
                f"📅 Дата: {display_date}\n"
                f"🕐 Время: {slot['slot_time']}",
                parse_mode="HTML"
            )
        except Exception as e:
            log.warning("Не удалось уведомить куратора: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# Открыть Meet (просто показать ссылку)
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("open_meet:"))
async def open_meet(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[1])
    uid        = callback.from_user.id
    student    = await StudentRepo.get_by_tid(uid)

    if student:
        booking = await ExamBookingRepo.get_active_by_student(student["id"])
        if booking and booking.get("google_meet_link"):
            await callback.answer(booking["google_meet_link"], show_alert=True)
            return

    await callback.answer("Ссылка не найдена.", show_alert=True)


# ──────────────────────────────────────────────────────────────────────────────
# Отмена записи
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[1])
    uid        = callback.from_user.id
    student    = await StudentRepo.get_by_tid(uid)

    if not student:
        await callback.answer("Ошибка.", show_alert=True)
        return

    booking = await ExamBookingRepo.get_active_by_student(student["id"])
    if not booking or booking["id"] != booking_id:
        await callback.answer("Запись не найдена или уже отменена.", show_alert=True)
        return

    slot_dt = datetime.fromisoformat(f"{booking['slot_date']} {booking['slot_time']}")
    delta   = (slot_dt - datetime.now()).total_seconds()

    if delta < 3600:
        await callback.answer(
            "⛔ Отменить нельзя — до зачёта меньше 1 часа.\n"
            "Свяжитесь с куратором напрямую.",
            show_alert=True
        )
        return

    display_date = format_date_for_display(booking["slot_date"])

    await ExamBookingRepo.cancel(booking_id)
    await ExamSlotRepo.unbook(booking["slot_id"])

    await callback.message.edit_text(
        f"✅ <b>Запись на зачёт отменена.</b>\n\n"
        f"Дата: {display_date}  Время: {booking['slot_time']}\n\n"
        f"Слот снова свободен — при желании можно записаться заново "
        f"через «🗓 Запись на зачёт»."
    )
    await callback.answer()

    # Уведомить куратора об отмене
    curator = await CuratorRepo.get_by_id(booking["curator_id"])
    if curator:
        try:
            await callback.bot.send_message(
                curator["telegram_id"],
                f"❌ <b>Ученик отменил запись на зачёт</b>\n\n"
                f"👨‍🎓 {booking['student_full_name']}\n"
                f"📅 {display_date}  🕐 {booking['slot_time']}\n\n"
                f"Слот снова свободен.",
                parse_mode="HTML"
            )
        except Exception as e:
            log.warning("Не удалось уведомить куратора об отмене: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# КУРАТОР — информация о зачётах
# ══════════════════════════════════════════════════════════════════════════════

async def show_curator_exam_info(message: Message, curator) -> None:
    """Куратор нажал «Запись на зачёт» — показать его расписание."""
    from bot.database import ExamSlotRepo, ExamBookingRepo

    dates  = await ExamSlotRepo.get_free_dates_by_curator(curator["id"])
    booked = await ExamBookingRepo.get_by_curator(curator["id"])

    lines = ["🗓 <b>Ваши зачёты</b>\n"]

    if booked:
        lines.append(f"📋 <b>Активных записей: {len(booked)}</b>")
        for b in booked[:10]:
            display = format_date_for_display(b["slot_date"])
            lines.append(f"  • {b['student_full_name']} — {display} {b['slot_time']}")
        if len(booked) > 10:
            lines.append(f"  ...и ещё {len(booked)-10}")
        lines.append("")

    if dates:
        lines.append(f"📅 <b>Свободных дат: {len(dates)}</b>")
        for d in dates:
            slots = await ExamSlotRepo.get_free_by_curator_and_date(curator["id"], d)
            display = format_date_for_display(d)
            lines.append(f"  • {display} — {len(slots)} свободных слотов")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "💡 Чтобы добавить новые слоты — нажмите «🗓 Создать слоты зачёта»\n"
        "Можно создавать слоты на несколько разных дат — ученики выберут удобный день."
    ]

    await message.answer("\n".join(lines), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# КУРАТОР — СОЗДАНИЕ СЛОТОВ (на несколько дней)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🗓 Создать слоты зачёта")
async def curator_create_slots_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid     = message.from_user.id
    curator = await CuratorRepo.get_by_tid(uid)

    if not curator:
        await message.answer(
            "⚠️ Вы не зарегистрированы как куратор.\n"
            "Обратитесь к администратору."
        )
        return

    await message.answer(
        "🗓 <b>Создание расписания зачётов</b>\n\n"
        "Вы можете создать слоты на любое количество дней.\n"
        "Ученики увидят все даты и выберут удобный день и время.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Шаг 1 из 5 — Введите дату</b>\n\n"
        "Формат: <code>ДД.ММ.ГГГГ</code>\n"
        "Пример: <code>24.06.2026</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(CreateExamSlots.waiting_date)


@router.message(CreateExamSlots.waiting_date, F.text == "❌ Отмена")
@router.message(CreateExamSlots.waiting_start, F.text == "❌ Отмена")
@router.message(CreateExamSlots.waiting_end, F.text == "❌ Отмена")
@router.message(CreateExamSlots.waiting_duration, F.text == "❌ Отмена")
@router.message(CreateExamSlots.waiting_meet, F.text == "❌ Отмена")
async def slots_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer("Отменено.", reply_markup=await get_menu(message.from_user.id))


@router.message(CreateExamSlots.waiting_date)
async def slots_date(message: Message, state: FSMContext) -> None:
    date_str = (message.text or "").strip()
    if not validate_date(date_str):
        await message.answer(
            "⚠️ Неверный формат даты.\n\n"
            "Введите дату в формате <code>ДД.ММ.ГГГГ</code>\n"
            "Пример: <code>24.06.2026</code>",
            parse_mode="HTML"
        )
        return

    # Проверить что дата не в прошлом
    dt = datetime.strptime(date_str, "%d.%m.%Y")
    if dt.date() < datetime.now().date():
        await message.answer(
            "⚠️ Нельзя создать слоты на прошедшую дату.\n\n"
            "Введите сегодняшнюю или будущую дату."
        )
        return

    await state.update_data(date=date_str)
    await message.answer(
        f"✅ Дата: <b>{date_str}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Шаг 2 из 5 — Время начала</b>\n\n"
        f"С какого времени начинаются зачёты?\n"
        f"Формат: <code>ЧЧ:ММ</code>  Пример: <code>14:00</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateExamSlots.waiting_start)


@router.message(CreateExamSlots.waiting_start)
async def slots_start(message: Message, state: FSMContext) -> None:
    t = (message.text or "").strip()
    try:
        datetime.strptime(t, "%H:%M")
    except ValueError:
        await message.answer(
            "⚠️ Неверный формат времени.\n"
            "Введите как: <code>14:00</code>",
            parse_mode="HTML"
        )
        return
    await state.update_data(start=t)
    await message.answer(
        f"✅ Начало: <b>{t}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Шаг 3 из 5 — Время окончания</b>\n\n"
        f"До какого времени продолжаются зачёты?\n"
        f"Пример: <code>16:00</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateExamSlots.waiting_end)


@router.message(CreateExamSlots.waiting_end)
async def slots_end(message: Message, state: FSMContext) -> None:
    t    = (message.text or "").strip()
    data = await state.get_data()
    try:
        t_end   = datetime.strptime(t, "%H:%M")
        t_start = datetime.strptime(data["start"], "%H:%M")
    except ValueError:
        await message.answer(
            "⚠️ Неверный формат. Введите как: <code>16:00</code>",
            parse_mode="HTML"
        )
        return

    if t_end <= t_start:
        await message.answer(
            f"⚠️ Время окончания должно быть позже начала.\n"
            f"Начало: <b>{data['start']}</b> — значит окончание должно быть после.",
            parse_mode="HTML"
        )
        return

    await state.update_data(end=t)
    await message.answer(
        f"✅ Окончание: <b>{t}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Шаг 4 из 5 — Длительность одного зачёта</b>\n\n"
        f"Сколько минут длится один зачёт?\n"
        f"Бот автоматически создаст слоты с таким интервалом.\n\n"
        f"Примеры: <code>10</code>  <code>15</code>  <code>20</code>  <code>30</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateExamSlots.waiting_duration)


@router.message(CreateExamSlots.waiting_duration)
async def slots_duration(message: Message, state: FSMContext) -> None:
    t    = (message.text or "").strip()
    data = await state.get_data()

    if not t.isdigit() or not (5 <= int(t) <= 120):
        await message.answer("⚠️ Введите число от 5 до 120 минут.")
        return

    dur    = int(t)
    slots  = generate_slots(data["start"], data["end"], dur)
    preview = "  ".join(slots[:6])
    more   = f"  ...и ещё {len(slots)-6}" if len(slots) > 6 else ""

    await state.update_data(duration=dur)
    await message.answer(
        f"✅ Длительность: <b>{dur} мин</b>\n\n"
        f"Будет создано <b>{len(slots)} слотов</b>:\n"
        f"<code>{preview}{more}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Шаг 5 из 5 — Ссылка Google Meet</b>\n\n"
        f"Вставьте ссылку на конференцию:\n"
        f"Пример: <code>https://meet.google.com/xxx-xxxx-xxx</code>\n\n"
        f"Если ссылки нет — отправьте <code>—</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreateExamSlots.waiting_meet)


@router.message(CreateExamSlots.waiting_meet)
async def slots_meet(message: Message, state: FSMContext) -> None:
    uid   = message.from_user.id
    data  = await state.get_data()
    meet  = (message.text or "").strip()
    if meet == "—":
        meet = ""

    slots   = generate_slots(data["start"], data["end"], data["duration"])
    curator = await CuratorRepo.get_by_tid(uid)

    if not curator:
        await message.answer("⚠️ Вы не зарегистрированы как куратор.")
        await state.clear()
        return
    if not slots:
        await message.answer("⚠️ Не удалось сгенерировать слоты. Проверьте время.")
        return

    date_db = format_date_for_db(data["date"])
    await ExamSlotRepo.add_many(curator["id"], date_db, slots, data["duration"], meet)
    await state.clear()

    from bot.handlers.user import get_menu
    kb = await get_menu(uid)

    slots_preview = "\n".join(f"  🕐 {s}" for s in slots)
    meet_line     = f"🔗 {meet}" if meet else "🔗 Ссылка не указана"

    await message.answer(
        f"✅ <b>Расписание создано!</b>\n\n"
        f"📅 Дата: <b>{data['date']}</b>\n"
        f"⏱ Длительность: <b>{data['duration']} мин</b>\n"
        f"🔢 Слотов создано: <b>{len(slots)}</b>\n"
        f"{meet_line}\n\n"
        f"<b>Все слоты:</b>\n"
        f"{slots_preview}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 Ученики уже видят эти слоты и могут записаться.\n"
        f"Можете создать ещё одну дату — нажмите «🗓 Создать слоты зачёта» снова.",
        parse_mode="HTML",
        reply_markup=kb
    )
