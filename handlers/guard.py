import secrets

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from database import get_bot, update_bot_field
from handlers.cards import owns

router = Router()

def _guard_text(bot: dict) -> str:
    username = (bot["username"] or "").lstrip("@")
    link = f"https://t.me/{username}?start={bot.get('user_secret')}"
    status = "🟢 включена" if bot.get("guard_enabled") else "🔴 выключена"
    return (
        "🔥 <b>Защита от бана</b>\n\n"
        "Когда защита включена, бот отвечает только тем, кто пришёл по "
        "вашей персональной ссылке. На обычный <code>/start</code> "
        "(в т.ч. от проверяющих) бот молчит — это снижает риск блокировки.\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"🔗 Ссылка для юзера:\n{link}"
    )

def _guard_kb(bot: dict) -> InlineKeyboardMarkup:
    bid = bot["id"]
    toggle = "🔴 Выключить защиту" if bot.get("guard_enabled") else "🟢 Включить защиту"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle, callback_data=f"guard_toggle:{bid}")],
            [
                InlineKeyboardButton(
                    text="♻️ Обновить ссылку", callback_data=f"guard_rotate:{bid}"
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bot:{bid}")],
        ]
    )

async def _show(callback: CallbackQuery, bot: dict) -> None:
    await callback.message.edit_text(
        _guard_text(bot), reply_markup=_guard_kb(bot), disable_web_page_preview=True
    )

@router.callback_query(F.data.startswith("guard:"))
async def open_guard(callback: CallbackQuery) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await _show(callback, bot)
    await callback.answer()

@router.callback_query(F.data.startswith("guard_toggle:"))
async def toggle_guard(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    new_val = 0 if bot.get("guard_enabled") else 1
    update_bot_field(bot_id, "guard_enabled", new_val)
    bot = get_bot(bot_id)
    await _show(callback, bot)
    await callback.answer("Готово ✅")

@router.callback_query(F.data.startswith("guard_rotate:"))
async def rotate_guard_link(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    update_bot_field(bot_id, "user_secret", secrets.token_urlsafe(6))
    bot = get_bot(bot_id)
    await _show(callback, bot)
    await callback.answer("Ссылка обновлена ♻️")
