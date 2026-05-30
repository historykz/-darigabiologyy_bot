"""
handlers/workbooks.py — Рабочие тетради с подробными инструкциями.
"""
from __future__ import annotations
import logging
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, FSInputFile
from bot.database import WorkbookRepo, UserRepo
from bot.states import GetWorkbook
from bot.keyboards import cancel_kb

log = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📚 Рабочие тетради")
async def workbooks_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid = message.from_user.id

    if not await UserRepo.has_access(uid):
        await message.answer(
            "⛔ <b>Доступ закрыт</b>\n\n"
            "У вас пока нет доступа к рабочим тетрадям.\n\n"
            "<b>Как получить доступ:</b>\n"
            f"1. Отправьте ваш Telegram ID куратору: введите /myid\n"
            "2. Куратор добавит вас в группу\n"
            "3. Вам придёт уведомление и откроется доступ",
            parse_mode="HTML"
        )
        return

    wbs = await WorkbookRepo.get_all()
    if not wbs:
        await message.answer(
            "📭 <b>Рабочих тетрадей пока нет</b>\n\n"
            "Администратор ещё не добавил материалы. "
            "Обратитесь к куратору."
        )
        return

    lines = [
        "📚 <b>Рабочие тетради</b>\n",
        "Ниже список всех доступных материалов.\n",
    ]
    for wb in wbs:
        lines.append(f"<b>№{wb['serial_number']}</b> — {wb['title']}  [{wb['file_type']}]")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "✏️ <b>Как получить файл:</b>",
        "Введите <b>номер</b> нужной тетради и отправьте.",
        "Например, чтобы получить первую — напишите: <code>1</code>",
    ]

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=cancel_kb())
    await state.set_state(GetWorkbook.waiting_number)


@router.message(GetWorkbook.waiting_number, F.text == "❌ Отмена")
async def workbook_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    from bot.handlers.user import get_menu
    await message.answer(
        "↩️ Возвращаемся в главное меню.",
        reply_markup=await get_menu(message.from_user.id)
    )


@router.message(GetWorkbook.waiting_number)
async def workbook_get(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()

    if not text.isdigit():
        wbs = await WorkbookRepo.get_all()
        nums = ", ".join(str(w["serial_number"]) for w in wbs)
        await message.answer(
            f"⚠️ Введите <b>только цифру</b> — номер тетради.\n\n"
            f"Доступные номера: <b>{nums}</b>\n\n"
            f"Например, напишите просто: <code>1</code>",
            parse_mode="HTML"
        )
        return

    serial = int(text)
    wb     = await WorkbookRepo.get_by_serial(serial)

    if not wb:
        wbs  = await WorkbookRepo.get_all()
        nums = ", ".join(str(w["serial_number"]) for w in wbs)
        await message.answer(
            f"❌ Рабочая тетрадь <b>№{serial}</b> не найдена.\n\n"
            f"Доступные номера: <b>{nums}</b>",
            parse_mode="HTML"
        )
        return

    await state.clear()
    from bot.handlers.user import get_menu
    kb = await get_menu(message.from_user.id)

    caption = (
        f"📘 <b>Рабочая тетрадь №{wb['serial_number']}</b>\n"
        f"📌 Тема: {wb['title']}\n"
        f"📄 Формат: {wb['file_type']}\n\n"
        f"📎 Файл прикреплён ниже.\n\n"
        f"💡 Скачайте файл и выполните задания. "
        f"Готовую работу сдайте через «📤 Сдать РТ»."
    )

    if wb["file_id"]:
        try:
            await message.answer_document(wb["file_id"], caption=caption,
                                          parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass

    fp = Path(wb["file_path"])
    if not fp.exists():
        await message.answer(
            "⚠️ <b>Файл не найден на сервере.</b>\n\n"
            "Сообщите об этом администратору — возможно файл был удалён.",
            parse_mode="HTML", reply_markup=kb
        )
        return

    sent = await message.answer_document(FSInputFile(fp), caption=caption,
                                         parse_mode="HTML", reply_markup=kb)
    if sent.document:
        await WorkbookRepo.update_file_id(serial, sent.document.file_id)
