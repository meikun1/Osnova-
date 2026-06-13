from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from .module import DirectLinkModule

class DirectLinkMiddleware(BaseMiddleware):

    def __init__(self, module: DirectLinkModule) -> None:
        super().__init__()
        self.module = module

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and self._is_start_command(event):
            bot_id = event.bot.id if event.bot else None
            if bot_id and await self.module.is_enabled_for(bot_id):
                return
        return await handler(event, data)

    @staticmethod
    def _is_start_command(message: Message) -> bool:
        text = (message.text or message.caption or "").strip()
        if not text.startswith("/start"):
            return False

        head = text.split(maxsplit=1)[0]
        command = head.split("@", 1)[0]
        return command == "/start"
