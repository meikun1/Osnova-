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

from database import (
    add_folder,
    delete_folder,
    get_bot,
    get_folder,
    get_folders,
    get_user_bots,
    update_bot_field,
)
from handlers.ui import edit_anchor, remember_anchor

router = Router()

class Folders(StatesGroup):
    waiting_for_name = State()

def _folders_kb(folders: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for folder in folders:
        builder.row(
            InlineKeyboardButton(
                text=f"📁 {folder['name']}", callback_data=f"folder:{folder['id']}"
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Новая папка", callback_data="folder_new"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    return builder.as_markup()

@router.callback_query(F.data == "folders")
async def show_folders(callback: CallbackQuery) -> None:
    folders = get_folders(callback.from_user.id)
    text = "📁 <b>Папки ботов</b>\n\n"
    text += "Выберите папку или создайте новую:" if folders else "Папок пока нет."
    await callback.message.edit_text(text, reply_markup=_folders_kb(folders))
    await callback.answer()

@router.callback_query(F.data == "folder_new")
async def new_folder(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Folders.waiting_for_name)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "➕ Пришлите название новой папки:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="folders")]
            ]
        ),
    )
    await callback.answer()

@router.message(Folders.waiting_for_name, F.text)
async def save_folder(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    add_folder(message.from_user.id, message.text.strip()[:40])
    folders = get_folders(message.from_user.id)
    text = "📁 <b>Папки ботов</b>\n\n✅ Папка создана!"
    await edit_anchor(message, data, text, _folders_kb(folders))

def _folder_view_kb(folder_id: int, bots: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for bot in bots:
        builder.row(
            InlineKeyboardButton(
                text=f"🤖 {bot['username']}", callback_data=f"bot:{bot['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить папку", callback_data=f"folder_del:{folder_id}"
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="folders"))
    return builder.as_markup()

@router.callback_query(F.data.startswith("folder:"))
async def open_folder(callback: CallbackQuery) -> None:
    folder_id = int(callback.data.split(":")[1])
    folder = get_folder(folder_id)
    if not folder or folder["owner_id"] != callback.from_user.id:
        await callback.answer("Папка не найдена.", show_alert=True)
        return
    bots = get_user_bots(callback.from_user.id, folder_id=folder_id)
    text = f"📁 <b>{folder['name']}</b>\n\n"
    text += "Боты в папке:" if bots else "В папке пока нет ботов."
    await callback.message.edit_text(text, reply_markup=_folder_view_kb(folder_id, bots))
    await callback.answer()

@router.callback_query(F.data.startswith("folder_del:"))
async def remove_folder(callback: CallbackQuery) -> None:
    folder_id = int(callback.data.split(":")[1])
    folder = get_folder(folder_id)
    if not folder or folder["owner_id"] != callback.from_user.id:
        await callback.answer("Папка не найдена.", show_alert=True)
        return
    delete_folder(folder_id)
    folders = get_folders(callback.from_user.id)
    await callback.message.edit_text(
        "🗑 Папка удалена. Боты из неё вернулись в общий список.",
        reply_markup=_folders_kb(folders),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("bot_to_folder:"))
async def choose_folder_for_bot(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":")[1])
    bot = get_bot(bot_id)
    if not bot or bot["owner_id"] != callback.from_user.id:
        await callback.answer("Бот не найден.", show_alert=True)
        return
    folders = get_folders(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗂 Без папки", callback_data=f"move_bot:{bot_id}:0")
    )
    for folder in folders:
        builder.row(
            InlineKeyboardButton(
                text=f"📁 {folder['name']}",
                callback_data=f"move_bot:{bot_id}:{folder['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bot:{bot_id}"))
    await callback.message.edit_text(
        "📁 В какую папку переложить бота?", reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("move_bot:"))
async def move_bot(callback: CallbackQuery) -> None:
    _, bot_id_str, folder_id_str = callback.data.split(":")
    bot_id = int(bot_id_str)
    bot = get_bot(bot_id)
    if not bot or bot["owner_id"] != callback.from_user.id:
        await callback.answer("Бот не найден.", show_alert=True)
        return
    folder_id = int(folder_id_str)
    update_bot_field(bot_id, "folder_id", folder_id or None)
    await callback.answer("Перемещено ✅", show_alert=False)

    callback.data = f"bot:{bot_id}"
    from handlers.manage_bots import show_bot_card

    await show_bot_card(callback)
