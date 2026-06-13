from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import direct_link_enabled, get_template
from templates import template_name

def _bot_template_name(bot: dict) -> str:
    tid = bot.get("template_id")
    if tid:
        t = get_template(tid)
        if t:
            return t["name"]
    return template_name(bot.get("template"))

def render_bot_card(bot: dict) -> tuple[str, InlineKeyboardMarkup]:
    username = bot["username"] or "—"
    miniapp = direct_link_enabled(bot.get("tg_id"))

    lines = [
        f"🤖 Бот: <b>{username}</b>",
        f"🔑 Токен: <code>{bot['token']}</code>",
        f"📋 Шаблон: {_bot_template_name(bot)}",
        "",
    ]
    if bot.get("guard_enabled"):
        clean = username.lstrip("@")
        link = f"https://t.me/{clean}?start={bot.get('user_secret')}"
        lines.append("🛡 Включена защита от бана!")
        lines.append(f"🔥 Ссылка для юзера: {link}")
        lines.append("")
    lines.append(f"💎 Мини-апп: {'Включено' if miniapp else 'Выключено'}")

    text = "\n".join(lines)

    bid = bot["id"]
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔄 Обновить статистику", callback_data=f"bot_refresh:{bid}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔌 Перезапуск", callback_data=f"bot_restart:{bid}"),
        InlineKeyboardButton(text="🔥 Защита от бана", callback_data=f"guard:{bid}"),
    )
    builder.row(
        InlineKeyboardButton(text="📨 Рассылка", callback_data=f"broadcast:{bid}"),
        InlineKeyboardButton(text="📈 Статистика", callback_data=f"stats:{bid}"),
    )
    builder.row(
        InlineKeyboardButton(text="📥 Выгрузить сессии", callback_data=f"export_sessions:{bid}")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Изменить шаблон", callback_data=f"template:{bid}")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"settings:{bid}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"bot_delete:{bid}"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"),
    )
    return text, builder.as_markup()

def owns(user_id: int, bot: dict | None) -> bool:
    return bool(bot and bot["owner_id"] == user_id)
