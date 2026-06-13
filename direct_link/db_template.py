from __future__ import annotations

from .storage import BotState

class HostDBStorage:

    def __init__(self, db) -> None:

        self.db = db

    async def get(self, bot_id: int) -> BotState | None:

        raise NotImplementedError

    async def init(self, bot_id: int, startapp_token: str) -> BotState:

        raise NotImplementedError

    async def set_enabled(self, bot_id: int, enabled: bool) -> None:

        raise NotImplementedError

    async def rotate_token(self, bot_id: int, new_token: str) -> BotState:

        raise NotImplementedError
