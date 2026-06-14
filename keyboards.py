from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_kb(user_bots: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🌐 Привязать свой домен", callback_data="domain_bind"
        )
    )

    for bot in user_bots:
        builder.row(
            InlineKeyboardButton(
                text=bot["username"] or "бот",
                callback_data=f"bot:{bot['id']}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="🗂 Управление ботами", callback_data="manage_bots"),
        InlineKeyboardButton(text="⚙️ Создать бота", callback_data="create_bot"),
    )
    builder.row(
        InlineKeyboardButton(
            text="📨 Настройки добавления", callback_data="add_settings_menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📣 Рассылка по токенам", callback_data="token_broadcast"
        )
    )
    builder.row(
        InlineKeyboardButton(text="📁 Папки ботов", callback_data="folders")
    )
    return builder.as_markup()
