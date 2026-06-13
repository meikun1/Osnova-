from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from child.runtime import get_runtime
from database import delete_bot, get_bot, get_user_bots
from handlers.cards import owns, render_bot_card

router = Router()

def _bots_list_kb(user_bots: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for bot in user_bots:
        running = get_runtime().is_running(bot.get("tg_id"))
        mark = "🟢" if (bot["enabled"] and running) else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {bot['username']}",
                callback_data=f"bot:{bot['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    return builder.as_markup()

@router.callback_query(F.data == "manage_bots")
async def show_bots_list(callback: CallbackQuery) -> None:
    user_bots = get_user_bots(callback.from_user.id)
    if not user_bots:
        await callback.answer("У вас пока нет ботов. Создайте бота!", show_alert=True)
        return
    await callback.message.edit_text(
        "🗂 <b>Управление ботами</b>\n\nВыберите бота:",
        reply_markup=_bots_list_kb(user_bots),
    )
    await callback.answer()

async def show_bot_card(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    text, kb = render_bot_card(bot)
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data.startswith("bot:"))
async def open_bot_card(callback: CallbackQuery) -> None:
    await show_bot_card(callback)

@router.callback_query(F.data.startswith("bot_refresh:"))
async def refresh_bot_card(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    text, kb = render_bot_card(bot)
    try:
        await callback.message.edit_text(
            text, reply_markup=kb, disable_web_page_preview=True
        )
    except Exception:
        pass
    await callback.answer("Статистика обновлена 🔄")

@router.callback_query(F.data.startswith("bot_delete:"))
async def confirm_delete(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить", callback_data=f"bot_delete_yes:{bot_id}"
                ),
                InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"bot:{bot_id}"),
            ]
        ]
    )
    await callback.message.edit_text(
        f"🗑 Удалить бота <b>{bot['username']}</b> из менеджера?", reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("bot_delete_yes:"))
async def do_delete(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return

    if bot.get("tg_id"):
        await get_runtime().stop_bot(bot["tg_id"])
    delete_bot(bot_id)
    user_bots = get_user_bots(callback.from_user.id)
    if not user_bots:
        from handlers.start import MAIN_PAGE_TEXT
        from keyboards import main_menu_kb

        await callback.message.edit_text(MAIN_PAGE_TEXT, reply_markup=main_menu_kb([]))
        await callback.answer("Бот удалён ✅")
        return
    await callback.message.edit_text(
        "🗂 <b>Управление ботами</b>\n\nВыберите бота:",
        reply_markup=_bots_list_kb(user_bots),
    )
    await callback.answer("Бот удалён ✅")
