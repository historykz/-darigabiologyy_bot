"""
handlers/checklists.py — Чек-листы с подробными инструкциями.
"""
from __future__ import annotations
import logging
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, FSInputFile
from bot.database import ChecklistRepo, UserRepo
from bot.states import GetChecklist
from bot.keyboards import cancel_kb

log = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "✅ Чек-листы")
async def checklists_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id

    if not await UserRepo.has_access(uid):
        await message.answer(
            "⛔ <b>Доступ закрыт</b>\n\n"
            "У вас нет доступа к чек-листам.\n\n"
            "<b>Как получить доступ:</b>\n"
            "1. Введите /myid — скопируйте ваш Telegram ID\n"
            "2. Передайте его куратору\n"
            "3. Куратор добавит вас, и вам придёт уведомление",
            parse_mode="HTML"
        )
        return

    cls = await ChecklistRepo.get_all()
    if not cls:
        await message.answer(
            "📭 <b>Чек-листов пока нет</b>\n\n"
            "Администратор ещё не добавил чек-листы. "
            "Обратитесь к куратору."
        )
        return

    lines = [
        "✅ <b>Чек-листы</b>\n",
        "Список доступных чек-листов:\n",
    ]
    for cl in cls:
        lines.append(f"<b>№{cl['serial_number']}</b> — {cl['title']}  [{cl['file_type']}]")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "✏️ <b>Как получить файл:</b>",
        "Введите <b>номер</b> чек-листа и отправьте.",
        "Например: <code>1</code>",
    ]

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=cancel_kb())
    await state.set_state(GetChecklist.waiting_number)


@router.message(GetChecklist.waiting_number, F.text == "❌ Отмена")
async def checklist_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer("↩️ Возвращаемся в главное меню.",
                         reply_markup=await get_menu(message.from_user.id))


@router.message(GetChecklist.waiting_number)
async def checklist_get(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()

    if not text.isdigit():
        cls  = await ChecklistRepo.get_all()
        nums = ", ".join(str(c["serial_number"]) for c in cls)
        await message.answer(
            f"⚠️ Введите <b>только номер</b> чек-листа.\n\n"
            f"Доступные номера: <b>{nums}</b>\n\n"
            f"Например: <code>1</code>",
            parse_mode="HTML"
        )
        return

    serial = int(text)
    cl     = await ChecklistRepo.get_by_serial(serial)

    if not cl:
        cls  = await ChecklistRepo.get_all()
        nums = ", ".join(str(c["serial_number"]) for c in cls)
        await message.answer(
            f"❌ Чек-лист <b>№{serial}</b> не найден.\n\n"
            f"Доступные номера: <b>{nums}</b>",
            parse_mode="HTML"
        )
        return

    await state.clear()
    from bot.handlers.user import get_menu
    kb = await get_menu(message.from_user.id)

    caption = (
        f"✅ <b>Чек-лист №{cl['serial_number']}</b>\n"
        f"📌 Тема: {cl['title']}\n"
        f"📄 Формат: {cl['file_type']}\n\n"
        f"📎 Файл прикреплён ниже.\n\n"
        f"💡 Используйте этот чек-лист для самопроверки перед зачётом."
    )

    if cl["file_id"]:
        try:
            await message.answer_document(cl["file_id"], caption=caption,
                                          parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass

    fp = Path(cl["file_path"])
    if not fp.exists():
        await message.answer(
            "⚠️ <b>Файл не найден на сервере.</b>\n\n"
            "Сообщите администратору.",
            parse_mode="HTML", reply_markup=kb
        )
        return

    sent = await message.answer_document(FSInputFile(fp), caption=caption,
                                         parse_mode="HTML", reply_markup=kb)
    if sent.document:
        await ChecklistRepo.update_file_id(serial, sent.document.file_id)
