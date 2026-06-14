from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramUnauthorizedError

from child.runner import build_dispatcher, make_bot
from config import BAN_CHECK_INTERVAL
from database import (
    delete_bot,
    get_all_bots,
    get_bot,
    get_bot_by_tg_id,
    get_launch_stats,
    get_proxy,
)

logger = logging.getLogger(__name__)

def _ban_text(bot_db: dict) -> str:
    uname = bot_db.get("username") or f"id={bot_db.get('tg_id')}"
    total = 0
    if bot_db.get("tg_id"):
        try:
            total = get_launch_stats(bot_db["tg_id"]).get("total", 0)
        except Exception:
            total = 0
    return (
        f"🚫 Ваш бот <b>{uname}</b> был удалён или забанен\n\n"
        f"👀 Запусков: <b>{total}</b>"
    )

class BotRuntime:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}
        self._bots: dict[int, Bot] = {}
        self._manager_bot: Bot | None = None
        self._banned: set[int] = set()
        self._health_task: asyncio.Task | None = None
        # Сериализует старт/стоп/рестарт ботов, чтобы не плодить
        # параллельные поллеры на один и тот же бот.
        self._op_lock = asyncio.Lock()

    def set_manager_bot(self, bot: Bot) -> None:
        self._manager_bot = bot

    async def _notify_owner(self, owner_id: int | None, text: str) -> None:
        if not (self._manager_bot and owner_id):
            return
        try:
            await self._manager_bot.send_message(owner_id, text)
        except Exception as e:
            logger.warning("owner notify failed (%s): %s", owner_id, e)

    async def send_test_ban(self, owner_id: int) -> bool:
        await self._notify_owner(
            owner_id,
            "🔔 <b>Тест уведомления</b> — так придёт сообщение при бане/удалении:\n\n"
            "🚫 Ваш бот <b>@your_bot</b> был удалён или забанен\n\n"
            "👀 Запусков: <b>0</b>",
        )
        return self._manager_bot is not None

    async def _on_banned(self, tg_id: int) -> None:
        if tg_id in self._banned:
            return
        self._banned.add(tg_id)
        bot_db = get_bot_by_tg_id(tg_id)

        text = _ban_text(bot_db) if bot_db else None
        await self.stop_bot(tg_id)
        if bot_db:
            delete_bot(bot_db["id"])
            await self._notify_owner(bot_db.get("owner_id"), text)
        logger.warning("child bot %s unauthorized — removed & owner notified", tg_id)

    async def start_all(self) -> None:
        for bot_db in get_all_bots():
            if bot_db.get("enabled") and bot_db.get("token"):
                await self.start_bot_db(bot_db)

    async def start_bot_db(self, bot_db: dict) -> None:
        async with self._op_lock:
            await self._start(bot_db)

    async def _start(self, bot_db: dict) -> None:
        token = bot_db.get("token")
        if not token:
            return
        proxy_url = None
        pid = bot_db.get("proxy_id")
        if pid:
            p = get_proxy(pid)
            if p:
                proxy_url = p["url"]
        bot = make_bot(token, proxy_url)
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError:

            await bot.session.close()
            tg = bot_db.get("tg_id")
            if not tg or tg not in self._banned:
                if tg:
                    self._banned.add(tg)
                await self._notify_owner(bot_db.get("owner_id"), _ban_text(bot_db))
            if bot_db.get("id"):
                delete_bot(bot_db["id"])
            logger.warning("bot id=%s unauthorized at start — removed", bot_db.get("id"))
            return
        except Exception as e:
            logger.warning("can't start bot id=%s: %s", bot_db.get("id"), e)
            await bot.session.close()
            return
        tg_id = me.id

        await self._stop(tg_id)
        self._banned.discard(tg_id)
        self._bots[tg_id] = bot
        self._tasks[tg_id] = asyncio.create_task(self._poll(bot))
        logger.info("started child bot @%s (id=%s)", me.username, tg_id)

    def start_health(self) -> None:
        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(self._health_loop())

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(BAN_CHECK_INTERVAL)
            for tg_id, bot in list(self._bots.items()):
                try:
                    await bot.get_me()
                except TelegramUnauthorizedError:
                    await self._on_banned(tg_id)
                except Exception:
                    pass

    async def _poll(self, bot: Bot) -> None:

        dp = build_dispatcher()
        try:
            await dp.start_polling(bot, handle_signals=False)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("polling crashed: %s", e)

    async def stop_bot(self, tg_id: int) -> None:
        async with self._op_lock:
            await self._stop(tg_id)

    async def _stop(self, tg_id: int) -> None:
        task = self._tasks.pop(tg_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        bot = self._bots.pop(tg_id, None)
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass

    async def restart_bot(self, bot_id: int) -> bool:
        bot_db = get_bot(bot_id)
        if not bot_db:
            return False
        async with self._op_lock:
            if bot_db.get("tg_id"):
                await self._stop(bot_db["tg_id"])
            await self._start(bot_db)
        return True

    def is_running(self, tg_id: int | None) -> bool:
        return bool(tg_id and tg_id in self._tasks)

    async def shutdown(self) -> None:
        async with self._op_lock:
            for tg_id in list(self._tasks):
                await self._stop(tg_id)

_runtime: BotRuntime | None = None

def get_runtime() -> BotRuntime:
    global _runtime
    if _runtime is None:
        _runtime = BotRuntime()
    return _runtime
