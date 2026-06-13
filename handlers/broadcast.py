import asyncio
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import get_bot, get_bot_user_ids
from handlers.cards import owns
from handlers.ui import remember_anchor

router = Router()

class Broadcast(StatesGroup):
    waiting_for_text = State()

def _back_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bot:{bot_id}")]
        ]
    )

@router.callback_query(F.data.startswith("broadcast:"))
async def start_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    audience = len(get_bot_user_ids(bot.get("tg_id"))) if bot.get("tg_id") else 0
    await state.set_state(Broadcast.waiting_for_text)
    await state.update_data(bot_id=bot_id)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        f"📨 <b>Рассылка</b> — {bot['username']}\n\n"
        f"Аудитория: <b>{audience}</b> чел.\n\n"
        "Пришлите текст сообщения для рассылки 👇",
        reply_markup=_back_kb(bot_id),
    )
    await callback.answer()

@router.message(Broadcast.waiting_for_text, F.text)
async def do_broadcast(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]
    await state.clear()
    chat = data.get("_anchor_chat")
    mid = data.get("_anchor_msg")

    with suppress(Exception):
        await message.delete()

    async def show(text: str, kb: InlineKeyboardMarkup | None = None) -> None:
        if chat and mid:
            with suppress(TelegramBadRequest):
                await message.bot.edit_message_text(
                    text, chat_id=chat, message_id=mid, reply_markup=kb
                )
                return
        await message.answer(text, reply_markup=kb)

    bot = get_bot(bot_id)
    if not bot or not bot.get("tg_id"):
        await show("Бот не найден.")
        return

    user_ids = get_bot_user_ids(bot["tg_id"])
    if not user_ids:
        await show(
            "Некому отправлять — бота ещё никто не запускал.", _back_kb(bot_id)
        )
        return

    text = message.text
    await show(f"Отправляю… 0/{len(user_ids)}")

    child = Bot(token=bot["token"])
    sent = failed = 0
    try:
        for i, uid in enumerate(user_ids, 1):
            try:
                await child.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1
            if i % 25 == 0:
                await show(f"Отправляю… {i}/{len(user_ids)}")
            await asyncio.sleep(0.05)
    finally:
        await child.session.close()

    await show(
        f"✅ Рассылка завершена.\n\nДоставлено: {sent}\nНе доставлено: {failed}",
        _back_kb(bot_id),
    )
