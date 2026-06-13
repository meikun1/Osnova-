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

from database import get_bot_user_ids, get_user_bots
from handlers.ui import remember_anchor

router = Router()

class TokenBroadcast(StatesGroup):
    waiting_for_text = State()

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
        ]
    )

@router.callback_query(F.data == "token_broadcast")
async def start(callback: CallbackQuery, state: FSMContext) -> None:
    bots = get_user_bots(callback.from_user.id)
    if not bots:
        await callback.answer("У вас пока нет ботов.", show_alert=True)
        return
    await state.set_state(TokenBroadcast.waiting_for_text)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "📣 <b>Рассылка по токенам</b>\n\n"
        f"Сообщение уйдёт через все ваши боты ({len(bots)} шт.) их юзерам.\n\n"
        "Пришлите текст рассылки 👇",
        reply_markup=_back_kb(),
    )
    await callback.answer()

@router.message(TokenBroadcast.waiting_for_text, F.text)
async def run(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
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

    bots = get_user_bots(message.from_user.id)
    text = message.text

    await show("Запускаю рассылку по токенам… ⏳")
    total_sent = total_failed = 0

    for bot in bots:
        tg_id = bot.get("tg_id")
        if not tg_id:
            continue
        user_ids = get_bot_user_ids(tg_id)
        if not user_ids:
            continue
        child = Bot(token=bot["token"])
        try:
            for uid in user_ids:
                try:
                    await child.send_message(uid, text)
                    total_sent += 1
                except Exception:
                    total_failed += 1
                await asyncio.sleep(0.05)
        finally:
            await child.session.close()

    await show(
        f"✅ Рассылка по токенам завершена.\n\n"
        f"Доставлено: {total_sent}\nНе доставлено: {total_failed}",
        _back_kb(),
    )
