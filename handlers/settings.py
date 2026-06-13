from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import get_bot, update_bot_field
from handlers.cards import owns
from handlers.ui import edit_anchor, remember_anchor

router = Router()

class Settings(StatesGroup):
    waiting_for_name = State()

def _settings_kb(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Прямая ссылка", callback_data=f"dl:{bot_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Выбор прокси", callback_data=f"proxy:{bot_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌍 Запуски", callback_data=f"stats:{bot_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Имя бота", callback_data=f"set_name:{bot_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔐 Авторизация", callback_data=f"set_soon:{bot_id}:auth"
                ),
                InlineKeyboardButton(
                    text="📢 Автоспам", callback_data=f"set_soon:{bot_id}:spam"
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bot:{bot_id}")],
        ]
    )

def _settings_text(bot: dict) -> str:
    return (
        f"⚙️ <b>Настройки</b> — {bot['username']}\n\n"
        "• <b>Прямая ссылка</b> — мини-апп по постоянной startapp-ссылке\n"
        "• <b>Выбор прокси</b> — пул прокси для поднятия ботов\n"
        "• <b>Запуски</b> — статистика запусков бота\n"
        "• <b>Имя бота</b> — изменить отображаемое имя бота\n"
        "• <b>Авторизация</b> — 🚧 скоро\n"
        "• <b>Автоспам</b> — 🚧 скоро"
    )

@router.callback_query(F.data.startswith("set_soon:"))
async def settings_soon(callback: CallbackQuery) -> None:
    await callback.answer("🚧 В разработке", show_alert=True)

@router.callback_query(F.data.startswith("settings:"))
async def open_settings(callback: CallbackQuery) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        _settings_text(bot), reply_markup=_settings_kb(bot["id"])
    )
    await callback.answer()

@router.callback_query(F.data.startswith("set_name:"))
async def ask_name(callback: CallbackQuery, state: FSMContext) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await state.set_state(Settings.waiting_for_name)
    await state.update_data(bot_id=bot_id)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "✏️ Пришлите новое имя бота (отображаемое имя, не username):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"settings:{bot_id}")]
            ]
        ),
    )
    await callback.answer()

@router.message(Settings.waiting_for_name, F.text)
async def save_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]
    await state.clear()

    bot = get_bot(bot_id)
    if not bot:
        await message.answer("Бот не найден.")
        return

    new_name = message.text.strip()[:64]
    child = Bot(token=bot["token"])
    try:
        await child.set_my_name(name=new_name)
        ok = True
    except Exception as e:
        ok = False
        err = str(e)
    finally:
        await child.session.close()

    if ok:
        await edit_anchor(
            message,
            data,
            f"✅ Имя бота изменено на: <b>{new_name}</b>",
            _settings_kb(bot_id),
        )
    else:
        await edit_anchor(
            message,
            data,
            f"⚠️ Не удалось изменить имя: {err}\n"
            "Telegram разрешает менять имя не чаще раза в сутки.",
            _settings_kb(bot_id),
        )
