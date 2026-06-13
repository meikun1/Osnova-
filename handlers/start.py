from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import add_user, get_menu_msg, get_user_bots, set_menu_msg
from keyboards import main_menu_kb

router = Router()

MAIN_PAGE_TEXT = (
    "<blockquote>🟣 У нас реализована функция обработки заявок в канал!\n\n"
    "❗️ Добавьте созданного вами бота в админы канала, и при подаче заявки "
    "бот напишет человеку первым!</blockquote>\n\n"
    "📋 <b>Ваши боты:</b>"
)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    add_user(message.chat.id, message.chat.username)
    kb = main_menu_kb(get_user_bots(message.chat.id))

    with suppress(Exception):
        await message.delete()

    anchor = get_menu_msg(message.chat.id)
    if anchor:
        with suppress(TelegramBadRequest):
            await message.bot.edit_message_text(
                MAIN_PAGE_TEXT,
                chat_id=message.chat.id,
                message_id=anchor,
                reply_markup=kb,
            )
            return

    sent = await message.answer(MAIN_PAGE_TEXT, reply_markup=kb)
    set_menu_msg(message.chat.id, sent.message_id)

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery) -> None:
    kb = main_menu_kb(get_user_bots(callback.from_user.id))
    await callback.message.edit_text(MAIN_PAGE_TEXT, reply_markup=kb)

    set_menu_msg(callback.from_user.id, callback.message.message_id)
    await callback.answer()
