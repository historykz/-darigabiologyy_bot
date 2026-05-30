"""
filters/roles.py — фильтры доступа по роли.
"""

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.database import UserRepo
from bot.config import ADMINS


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        uid = event.from_user.id if event.from_user else 0
        if uid in ADMINS:
            return True
        role = await UserRepo.get_role(uid)
        return role == "admin"


class IsCurator(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        uid = event.from_user.id if event.from_user else 0
        role = await UserRepo.get_role(uid)
        return role in ("curator", "admin")


class IsStudent(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        uid = event.from_user.id if event.from_user else 0
        role = await UserRepo.get_role(uid)
        return role in ("student", "curator", "admin")


class HasAccess(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        uid = event.from_user.id if event.from_user else 0
        return await UserRepo.has_access(uid)
