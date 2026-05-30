"""
handlers/user.py
/start, /help, /myid, профиль — с подробными объяснениями для каждой роли.
"""

from __future__ import annotations
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.database import UserRepo, StudentRepo, CuratorRepo, GroupRepo
from bot.keyboards import main_menu_user, main_menu_curator, main_menu_admin

log = logging.getLogger(__name__)
router = Router()


async def get_menu(telegram_id: int):
    role = await UserRepo.get_role(telegram_id)
    if role == "admin":   return main_menu_admin()
    if role == "curator": return main_menu_curator()
    return main_menu_user()


# ══════════════════════════════════════════════════════════════════════════════
# /start — подробное приветствие по роли
# ══════════════════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    uid  = message.from_user.id
    name = message.from_user.full_name

    await UserRepo.upsert(uid, message.from_user.username, name)
    role = await UserRepo.get_role(uid)
    kb   = await get_menu(uid)

    if role == "admin":
        text = (
            f"👋 Привет, <b>{name}</b>! Вы вошли как <b>⚙️ Администратор</b>.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 <b>Ваши возможности:</b>\n\n"
            f"⚙️ <b>Админ-панель</b> — полное управление системой:\n"
            f"   • Добавляйте, удаляйте и переименовывайте рабочие тетради\n"
            f"   • Управляйте чек-листами\n"
            f"   • Назначайте кураторов и создавайте группы\n"
            f"   • Добавляйте учеников и выдавайте доступы\n"
            f"   • Экспортируйте данные в Excel\n\n"
            f"👥 <b>Мои группы</b> — создавайте группы и управляйте учениками\n\n"
            f"📥 <b>Сданные РТ</b> — просматривайте все сданные работы\n\n"
            f"🗓 <b>Создать слоты зачёта</b> — настройте расписание зачётов\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>Подсказка:</b> Используйте /help для справки по любой функции."
        )

    elif role == "curator":
        curator = await CuratorRepo.get_by_tid(uid)
        groups  = await GroupRepo.get_by_curator(curator["id"]) if curator else []
        text = (
            f"👋 Привет, <b>{name}</b>! Вы вошли как <b>👨‍🏫 Куратор</b>.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 <b>Ваши возможности:</b>\n\n"
            f"👥 <b>Мои группы</b> — управление группами:\n"
            f"   • Создавайте новые группы кнопкой «➕ Создать новую группу»\n"
            f"   • Нажмите на группу → добавьте или удалите учеников\n"
            f"   • Ученик получит уведомление при добавлении\n\n"
            f"👨‍🎓 <b>Мои ученики</b> — список всех ваших учеников по всем группам\n\n"
            f"📥 <b>Сданные РТ</b> — PDF-файлы от учеников:\n"
            f"   • Выбирайте фильтр: «Все» или конкретная группа\n"
            f"   • PDF приходят вам автоматически при сдаче\n\n"
            f"🗓 <b>Создать слоты зачёта</b> — настройте расписание:\n"
            f"   • Укажите дату, начало/конец и длительность слота\n"
            f"   • Добавьте ссылку Google Meet\n"
            f"   • Ученики сами выберут удобное время\n\n"
            f"📚 <b>Рабочие тетради</b> и ✅ <b>Чек-листы</b> — доступны вам как и ученикам\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Ваших групп сейчас: <b>{len(groups)}</b>\n"
            f"💡 Чтобы добавить ученика — сначала создайте группу через «👥 Мои группы»"
        )

    elif role == "student":
        student = await StudentRepo.get_by_tid(uid)
        curator_name = "—"
        group_name   = "—"
        if student:
            if student["curator_id"]:
                cur = await CuratorRepo.get_by_id(student["curator_id"])
                if cur: curator_name = cur["full_name"]
            if student["group_id"]:
                grp = await GroupRepo.get_by_id(student["group_id"])
                if grp: group_name = grp["title"]
        text = (
            f"👋 Привет, <b>{name}</b>! Вы вошли как <b>👨‍🎓 Ученик</b>.\n\n"
            f"👥 Группа: <b>{group_name}</b>\n"
            f"👨‍🏫 Куратор: <b>{curator_name}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 <b>Что вы можете делать:</b>\n\n"
            f"📚 <b>Рабочие тетради</b> — скачать учебные материалы:\n"
            f"   • Нажмите кнопку → увидите список всех РТ с номерами\n"
            f"   • Введите номер (например: 1) → получите файл\n\n"
            f"📤 <b>Сдать РТ</b> — отправить выполненную работу куратору:\n"
            f"   • Введите ФИО → отправляйте фото страниц по одному\n"
            f"   • Нажмите «📄 Отправить в PDF» — бот соберёт всё в PDF\n"
            f"   • PDF автоматически уйдёт куратору\n\n"
            f"✅ <b>Чек-листы</b> — скачать чек-листы по номеру\n\n"
            f"🗓 <b>Запись на зачёт</b> — выбрать дату и время:\n"
            f"   • Выберите день → выберите свободный слот\n"
            f"   • За 10 минут и в момент начала придёт напоминание\n"
            f"   • Отменить запись можно если до зачёта больше 1 часа\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>Подсказка:</b> /myid — узнать свой Telegram ID"
        )

    else:
        text = (
            f"👋 Привет, <b>{name}</b>!\n\n"
            f"Вы зарегистрированы в системе, но у вас пока нет доступа к материалам.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Что нужно сделать:</b>\n\n"
            f"1️⃣ Сообщите куратору или администратору свой <b>Telegram ID</b>:\n"
            f"   Отправьте /myid → скопируйте цифры → передайте куратору\n\n"
            f"2️⃣ После добавления в группу вам придёт уведомление\n"
            f"   и откроются все функции бота.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Ваш Telegram ID: <code>{uid}</code>"
        )

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# /help — подробная справка
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    uid  = message.from_user.id
    role = await UserRepo.get_role(uid)

    base = (
        "📖 <b>Полная справка по боту</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📚 <b>РАБОЧИЕ ТЕТРАДИ</b>\n"
        "Нажмите «📚 Рабочие тетради» — бот покажет список всех доступных РТ "
        "с номерами и названиями. Просто введите нужный номер и получите файл. "
        "Поддерживаются PDF, Word, фото и любые другие форматы.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📤 <b>СДАЧА РАБОЧЕЙ ТЕТРАДИ</b>\n"
        "1. Нажмите «📤 Сдать РТ»\n"
        "2. Введите ФИО полностью (например: Иванов Иван Иванович)\n"
        "3. Фотографируйте страницы и отправляйте по одному — "
        "бот принимает каждое фото и считает их\n"
        "4. Когда все страницы отправлены — нажмите «📄 Отправить в PDF»\n"
        "5. Бот соберёт все фото в один PDF и автоматически отправит куратору\n"
        "❗ Фотографируйте при хорошем освещении, текст должен быть читаемым\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>ЧЕК-ЛИСТЫ</b>\n"
        "Аналогично рабочим тетрадям — введите номер и получите файл.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🗓 <b>ЗАПИСЬ НА ЗАЧЁТ</b>\n"
        "1. Нажмите «🗓 Запись на зачёт»\n"
        "2. Выберите дату из доступных\n"
        "3. Выберите свободное время\n"
        "4. Получите подтверждение со ссылкой Google Meet\n"
        "⏰ За 10 минут до зачёта придёт напоминание\n"
        "⏰ В момент начала придёт сообщение со ссылкой\n"
        "❌ Отменить можно только если до зачёта больше 1 часа\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>МОЙ ПРОФИЛЬ</b>\n"
        "Показывает вашу роль, группу, куратора и статус доступа.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🆘 <b>КОМАНДЫ</b>\n"
        "/start — открыть главное меню\n"
        "/myid  — узнать свой Telegram ID\n"
        "/help  — эта справка\n"
    )

    curator_extra = ""
    if role in ("curator", "admin"):
        curator_extra = (
            "\n━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍🏫 <b>ФУНКЦИИ КУРАТОРА</b>\n\n"
            "👥 <b>Мои группы</b> — нажмите, чтобы:\n"
            "   • Создать новую группу (кнопка «➕ Создать новую группу»)\n"
            "   • Нажать на группу → увидеть учеников\n"
            "   • Добавить ученика (нужен его Telegram ID — пусть отправит /myid)\n"
            "   • Удалить ученика из группы\n"
            "   • Удалить группу\n\n"
            "📥 <b>Сданные РТ</b> — нажмите и выберите фильтр:\n"
            "   «📋 Все сдачи» или конкретную группу\n\n"
            "🗓 <b>Создать слоты зачёта</b>:\n"
            "   • Укажите дату → время начала → время конца → длительность слота\n"
            "   • Бот автоматически создаст все промежутки (14:00, 14:15, 14:30...)\n"
            "   • Вставьте ссылку Google Meet (или «—» чтобы пропустить)\n"
            "   • Ученики увидят только свободные слоты и выберут сами\n"
            "   • Создавайте слоты на несколько разных дат — ученики выберут удобный день\n"
        )

    admin_extra = ""
    if role == "admin":
        admin_extra = (
            "\n━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>ФУНКЦИИ АДМИНИСТРАТОРА</b>\n\n"
            "Откройте «⚙️ Админ-панель» для:\n"
            "   • Добавления РТ и чек-листов (отправьте файл → введите название)\n"
            "   • Назначения кураторов (нужен Telegram ID куратора)\n"
            "   • Добавления учеников в группы\n"
            "   • Выдачи/отзыва доступа к материалам\n"
            "   • Экспорта сдач и зачётов в Excel\n"
            "   • Очистки списков\n\n"
            "💡 Все назначенные кураторы и ученики получают уведомления автоматически.\n"
        )

    await message.answer(base + curator_extra + admin_extra, parse_mode="HTML")


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    uid = message.from_user.id
    await message.answer(
        f"🆔 <b>Ваш Telegram ID:</b>\n\n"
        f"<code>{uid}</code>\n\n"
        f"📋 Скопируйте эти цифры и передайте куратору или администратору — "
        f"они используют ID чтобы добавить вас в систему.",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# ПРОФИЛЬ
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "👤 Мой профиль")
async def my_profile(message: Message) -> None:
    uid  = message.from_user.id
    user = await UserRepo.get(uid)
    if not user:
        await message.answer("Профиль не найден. Напишите /start")
        return

    role_icons = {"admin": "⚙️ Администратор", "curator": "👨‍🏫 Куратор",
                  "student": "👨‍🎓 Ученик", "user": "👤 Пользователь"}
    has_acc = user["role"] in ("admin", "curator") or bool(user["has_access"])

    lines = [
        "👤 <b>Мой профиль</b>\n",
        f"🆔 Telegram ID: <code>{uid}</code>",
        f"👤 Имя: {message.from_user.full_name}",
        f"🔖 Username: @{message.from_user.username or '—'}",
        f"🎭 Роль: {role_icons.get(user['role'], '👤 Пользователь')}",
        f"✅ Доступ к материалам: {'Есть ✅' if has_acc else 'Нет ❌'}",
    ]

    if user["role"] == "student":
        student = await StudentRepo.get_by_tid(uid)
        if student:
            group_title  = "—"
            curator_name = "—"
            if student["group_id"]:
                grp = await GroupRepo.get_by_id(student["group_id"])
                if grp: group_title = grp["title"]
            if student["curator_id"]:
                cur = await CuratorRepo.get_by_id(student["curator_id"])
                if cur: curator_name = cur["full_name"]
            lines += [f"👥 Группа: {group_title}", f"👨‍🏫 Куратор: {curator_name}"]

    elif user["role"] == "curator":
        curator = await CuratorRepo.get_by_tid(uid)
        if curator:
            groups = await GroupRepo.get_by_curator(curator["id"])
            lines.append(f"👥 Групп: {len(groups)}")
            for g in groups:
                cnt = len(await StudentRepo.get_by_group(g["id"]))
                lines.append(f"   • {g['title']} ({cnt} учеников)")

    if not has_acc and user["role"] == "user":
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "ℹ️ <b>Как получить доступ:</b>",
            f"Отправьте свой ID куратору: <code>{uid}</code>",
            "Он добавит вас в группу и откроет все материалы."
        ]

    await message.answer("\n".join(lines), parse_mode="HTML")
