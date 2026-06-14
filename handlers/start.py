from contextlib import suppress

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import add_user, get_user_bots, set_menu_msg
from keyboards import main_menu_kb

router = Router()

MAIN_PAGE_TEXT = (
    "<blockquote>🟣 У нас реализована функция обработки заявок в канал!\n\n"
    "❗️ Добавьте созданного вами бота в админы канала, и при подаче заявки "
    "бот напишет человеку первым!</blockquote>\n\n"
    "📋 <b>Ваши боты:</b>"
)

async def _purge_recent(bot, chat_id: int, last_id: int, window: int = 100) -> None:
    """Сносит недавние сообщения в чате (старые меню, промпты, мусор).
    Пачкой через delete_messages, с фолбэком на поштучное удаление."""
    start_id = max(1, last_id - window)
    ids = list(range(start_id, last_id + 1))
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id, chunk)
        except Exception:
            for mid in chunk:
                with suppress(Exception):
                    await bot.delete_message(chat_id, mid)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    add_user(message.chat.id, message.chat.username)
    kb = main_menu_kb(get_user_bots(message.chat.id), message.chat.id)

    # Чистим чат: сносим старые меню и накопившийся хлам.
    await _purge_recent(message.bot, message.chat.id, message.message_id)

    sent = await message.answer(MAIN_PAGE_TEXT, reply_markup=kb)
    set_menu_msg(message.chat.id, sent.message_id)

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery) -> None:
    kb = main_menu_kb(get_user_bots(callback.from_user.id), callback.from_user.id)
    await callback.message.edit_text(MAIN_PAGE_TEXT, reply_markup=kb)

    set_menu_msg(callback.from_user.id, callback.message.message_id)
    await callback.answer()
