from __future__ import annotations

from typing import Protocol, TypedDict

class BotState(TypedDict):
    enabled: bool
    startapp_token: str
    token_version: int

class DirectLinkStorage(Protocol):
    async def get(self, bot_id: int) -> BotState | None:
        ...

    async def init(self, bot_id: int, startapp_token: str) -> BotState:
        ...

    async def set_enabled(self, bot_id: int, enabled: bool) -> None: ...

    async def rotate_token(self, bot_id: int, new_token: str) -> BotState:
        ...
