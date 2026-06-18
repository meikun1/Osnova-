"""Проверка Telegram WebApp initData для панели владельца.

Используется ключ MANAGER_BOT_TOKEN, потому что панель открывается с
бот-менеджера, а не с дочернего бота. Заголовок: X-Telegram-Init-Data.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from config import ADMIN_IDS, MANAGER_BOT_TOKEN
from direct_link.telegram import InitDataError, verify_init_data

# initData живёт сутки — для панели достаточно с запасом.
_MAX_AGE = 24 * 60 * 60


async def verify_panel_user(
    x_telegram_init_data: str = Header("", alias="X-Telegram-Init-Data"),
) -> dict:
    """FastAPI dependency: проверяет initData и возвращает текущего юзера.

    Возвращает: {"id": int, "username": str, "is_admin": bool}
    """
    if not MANAGER_BOT_TOKEN:
        raise HTTPException(500, "manager token not configured")
    if not x_telegram_init_data:
        raise HTTPException(401, "missing X-Telegram-Init-Data header")
    try:
        tg_user, _start_param = verify_init_data(
            x_telegram_init_data, MANAGER_BOT_TOKEN, _MAX_AGE
        )
    except InitDataError as e:
        raise HTTPException(401, f"invalid initData: {e}")
    return {
        "id": tg_user.id,
        "username": tg_user.username,
        "is_admin": tg_user.id in ADMIN_IDS,
    }


async def require_admin(user: dict) -> None:
    if not user.get("is_admin"):
        raise HTTPException(403, "admin only")
