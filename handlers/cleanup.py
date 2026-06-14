from __future__ import annotations

from contextlib import suppress

from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def delete_stray(message: Message) -> None:
    """Глобальный уборщик. Срабатывает последним — только на сообщения,
    которые не подхватил ни один другой хендлер (рандомный текст, стикеры,
    пересланное, ввод не в том месте и т.п.). Чистит чат от мусора.

    Уведомления бота (баны/статусы) — это исходящие сообщения, их не трогает.
    """
    with suppress(Exception):
        await message.delete()
