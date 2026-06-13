from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from database import (
    get_bot,
    get_launch_stats,
    get_recent_launches,
)
from handlers.cards import owns

router = Router()

def _stats_text(bot: dict) -> str:
    tg_id = bot.get("tg_id")
    stats = get_launch_stats(tg_id) if tg_id else {"total": 0, "unique": 0, "by_geo": []}
    recent = get_recent_launches(tg_id) if tg_id else []

    lines = [
        f"📈 <b>Статистика по гео</b> — {bot['username']}",
    ]

    if stats["by_geo"]:
        lines.append("\n🌍 По гео:")
        for geo, cnt in stats["by_geo"]:
            lines.append(f"  • {geo}: {cnt}")
    else:
        lines.append("\n🌍 По гео пока нет данных.")

    if recent:
        lines.append("\n🕓 Последние запуски (id — гео):")
        for r in recent:
            ts = datetime.fromtimestamp(r["created_at"], tz=timezone.utc).strftime(
                "%d.%m %H:%M"
            )
            uname = f"@{r['username']}" if r["username"] else ""
            lines.append(
                f"  • <code>{r['user_id']}</code> — {r['geo'] or '—'} {uname} ({ts})"
            )
    else:
        lines.append("\nПока никто не запускал бота.")

    return "\n".join(lines)

def _stats_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить", callback_data=f"stats_refresh:{bot_id}"
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bot:{bot_id}")],
        ]
    )

async def _render(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            _stats_text(bot), reply_markup=_stats_kb(bot_id)
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("stats:"))
async def open_stats(callback: CallbackQuery) -> None:
    await _render(callback)
    await callback.answer()

@router.callback_query(F.data.startswith("stats_refresh:"))
async def refresh_stats(callback: CallbackQuery) -> None:
    await _render(callback)
    await callback.answer("Обновлено 🔄")
