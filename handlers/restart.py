from aiogram import F, Router
from aiogram.types import CallbackQuery

from child.runtime import get_runtime
from database import get_bot, update_bot_field
from handlers.cards import owns, render_bot_card

router = Router()

@router.callback_query(F.data.startswith("bot_restart:"))
async def restart_bot(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return

    await callback.answer("Перезапускаю… ⏳")
    update_bot_field(bot_id, "enabled", 1)
    ok = await get_runtime().restart_bot(bot_id)

    bot = get_bot(bot_id)
    text, kb = render_bot_card(bot)
    prefix = "✅ Бот перезапущен!\n\n" if ok else "⚠️ Не удалось перезапустить.\n\n"
    try:
        await callback.message.edit_text(
            prefix + text, reply_markup=kb, disable_web_page_preview=True
        )
    except Exception:
        pass
