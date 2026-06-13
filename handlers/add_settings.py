from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_bot, get_user_bots, update_bot_field
from handlers.ui import edit_anchor, remember_anchor

router = Router()

DEFAULT_WELCOME = "Привет! 👋 Спасибо за заявку, рады видеть вас в нашем канале!"

class AddSettings(StatesGroup):
    waiting_for_welcome = State()

@router.callback_query(F.data == "add_settings_menu")
async def pick_bot(callback: CallbackQuery) -> None:
    bots = get_user_bots(callback.from_user.id)
    if not bots:
        await callback.answer("У вас пока нет ботов.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for bot in bots:
        builder.row(
            InlineKeyboardButton(
                text=bot["username"], callback_data=f"add_settings:{bot['id']}"
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    await callback.message.edit_text(
        "📨 <b>Настройки добавления</b>\n\nВыберите бота:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()

def _settings_kb(bot: dict) -> InlineKeyboardMarkup:
    approve = "✅ Авто-приём: вкл" if bot["auto_approve"] else "❌ Авто-приём: выкл"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=approve, callback_data=f"toggle_approve:{bot['id']}")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Приветствие", callback_data=f"set_welcome:{bot['id']}")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="add_settings_menu")
    )
    return builder.as_markup()

def _settings_text(bot: dict) -> str:
    welcome = bot["welcome_message"] or DEFAULT_WELCOME
    approve = "включён" if bot["auto_approve"] else "выключен"
    return (
        f"📨 <b>Настройки добавления</b> — {bot['username']}\n\n"
        "Когда человек подаёт заявку в канал, бот напишет ему первым.\n\n"
        f"• Авто-приём заявки: <b>{approve}</b>\n"
        f"• Приветствие:\n<i>{welcome}</i>"
    )

def _owns(callback: CallbackQuery, bot: dict | None) -> bool:
    return bool(bot and bot["owner_id"] == callback.from_user.id)

@router.callback_query(F.data.startswith("add_settings:"))
async def open_settings(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not _owns(callback, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_approve:"))
async def toggle_approve(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not _owns(callback, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    update_bot_field(bot_id, "auto_approve", 0 if bot["auto_approve"] else 1)
    bot = get_bot(bot_id)
    await callback.message.edit_text(_settings_text(bot), reply_markup=_settings_kb(bot))
    await callback.answer("Готово ✅")

@router.callback_query(F.data.startswith("set_welcome:"))
async def ask_welcome(callback: CallbackQuery, state: FSMContext) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not _owns(callback, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await state.set_state(AddSettings.waiting_for_welcome)
    await state.update_data(bot_id=bot_id)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "✏️ Пришлите текст приветствия, которое бот отправит человеку при заявке:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"add_settings:{bot_id}")]
            ]
        ),
    )
    await callback.answer()

@router.message(AddSettings.waiting_for_welcome, F.text)
async def save_welcome(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]
    await state.clear()
    update_bot_field(bot_id, "welcome_message", message.text.strip())

    bot = get_bot(bot_id)
    await edit_anchor(
        message,
        data,
        "✅ Приветствие сохранено!\n\n" + _settings_text(bot),
        _settings_kb(bot),
    )
