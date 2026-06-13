import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from child.runtime import get_runtime
from database import add_bot, get_bot, token_exists, update_bot_field
from handlers.ui import edit_anchor, remember_anchor

router = Router()

TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")

class CreateBot(StatesGroup):
    waiting_for_token = State()

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="main_menu")]
        ]
    )

@router.callback_query(F.data == "create_bot")
async def start_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateBot.waiting_for_token)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "⚙️ <b>Создание бота</b>\n\n"
        "1. Откройте @BotFather и отправьте <code>/newbot</code>\n"
        "2. Придумайте имя и username\n"
        "3. Скопируйте токен и пришлите его сюда 👇\n\n"
        "<i>Пример: 123456789:AaBbCcDdEe...</i>",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()

@router.message(CreateBot.waiting_for_token, F.text)
async def receive_token(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    token = message.text.strip()

    if not TOKEN_RE.match(token):

        await edit_anchor(
            message,
            data,
            "❌ Это не похоже на токен. Пришлите токен от @BotFather целиком.",
            _cancel_kb(),
        )
        return

    if token_exists(token):
        await edit_anchor(
            message, data, "⚠️ Этот бот уже добавлен.", _cancel_kb()
        )
        return

    child_bot = Bot(token=token)
    try:
        me = await child_bot.get_me()
    except TelegramUnauthorizedError:
        await edit_anchor(
            message,
            data,
            "❌ Токен недействителен (отклонён Telegram). Проверьте и пришлите снова.",
            _cancel_kb(),
        )
        return
    finally:
        await child_bot.session.close()

    bot_id = add_bot(
        owner_id=message.from_user.id,
        token=token,
        username=f"@{me.username}",
        tg_id=me.id,
    )
    await state.clear()

    await get_runtime().start_bot_db(get_bot(bot_id))

    await edit_anchor(
        message,
        data,
        f"✅ Бот <b>@{me.username}</b> успешно добавлен и запущен!\n\n"
        "Теперь добавьте его в админы вашего закрытого канала, "
        "и настройте обработку заявок в разделе «Настройки добавления».",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]
            ]
        ),
    )
