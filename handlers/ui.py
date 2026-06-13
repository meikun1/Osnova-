from __future__ import annotations

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

async def remember_anchor(callback: CallbackQuery, state: FSMContext) -> None:
    msg = callback.message
    if msg is not None:
        await state.update_data(_anchor_chat=msg.chat.id, _anchor_msg=msg.message_id)

async def edit_anchor(
    message: Message,
    data: dict,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    with suppress(Exception):
        await message.delete()
    chat = data.get("_anchor_chat")
    mid = data.get("_anchor_msg")
    if chat and mid:
        with suppress(TelegramBadRequest):
            await message.bot.edit_message_text(
                text, chat_id=chat, message_id=mid, reply_markup=reply_markup
            )
            return

    await message.answer(text, reply_markup=reply_markup)
