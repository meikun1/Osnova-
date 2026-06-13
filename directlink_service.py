from __future__ import annotations

from fastapi import HTTPException, Request

from config import (
    DIRECT_LINK_MANUAL_URL,
    DIRECT_LINK_REDIRECT_URL,
    DIRECT_LINK_SESSION_SECRET,
)
from database import dl_get, dl_init, dl_rotate, dl_set_enabled, get_bot_by_tg_id
from direct_link import DirectLinkConfig, DirectLinkModule
from direct_link.storage import BotState

class DBDirectLinkStorage:

    async def get(self, bot_id: int) -> BotState | None:
        return dl_get(bot_id)

    async def init(self, bot_id: int, startapp_token: str) -> BotState:
        return dl_init(bot_id, startapp_token)

    async def set_enabled(self, bot_id: int, enabled: bool) -> None:
        dl_set_enabled(bot_id, enabled)

    async def rotate_token(self, bot_id: int, new_token: str) -> BotState:
        return dl_rotate(bot_id, new_token)

async def _get_bot_token(bot_id: int) -> str | None:
    bot = get_bot_by_tg_id(bot_id)
    return bot["token"] if bot else None

async def _get_bot_username(bot_id: int) -> str | None:
    bot = get_bot_by_tg_id(bot_id)
    if not bot or not bot["username"]:
        return None
    return bot["username"].lstrip("@")

async def _verify_admin(request: Request, bot_id: int) -> None:
    header = request.headers.get("X-Admin-Secret", "")
    if header != DIRECT_LINK_SESSION_SECRET:
        raise HTTPException(403, "forbidden")

_module: DirectLinkModule | None = None

def get_module() -> DirectLinkModule:
    global _module
    if _module is None:
        _module = DirectLinkModule(
            DirectLinkConfig(
                session_secret=DIRECT_LINK_SESSION_SECRET,
                redirect_url=DIRECT_LINK_REDIRECT_URL,
                manual_url=DIRECT_LINK_MANUAL_URL,
            ),
            storage=DBDirectLinkStorage(),
            get_bot_token=_get_bot_token,
            get_bot_username=_get_bot_username,
            verify_admin=_verify_admin,
        )
    return _module
