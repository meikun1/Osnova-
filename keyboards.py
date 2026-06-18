from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from database import user_domains_list


def _panel_url_for(user_id: int) -> str | None:
    """Возвращает URL панели владельца, если у юзера есть домен с готовым SSL.
    Без такого домена WebApp Telegram не примет (нужен HTTPS на живом домене)."""
    if user_id is None:
        return None
    domains = [d for d in user_domains_list(user_id) if d.get("ssl_notified")]
    if not domains:
        return None
    return f"https://{domains[-1]['domain']}/panel"


def main_menu_kb(user_bots: list[dict], user_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    panel_url = _panel_url_for(user_id)
    if panel_url:
        builder.row(
            InlineKeyboardButton(text="🛠 Открыть панель", web_app=WebAppInfo(url=panel_url))
        )

    if user_id is not None and user_id in ADMIN_IDS:
        builder.row(
            InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")
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
