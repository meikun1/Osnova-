from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from child.runtime import get_runtime
from config import (
    MANAGER_BOT_TOKEN,
    PANEL_BASE_URL,
    PANEL_MENU_LABEL,
    RUN_WEB,
    WEB_HOST,
    WEB_PORT,
)
from database import init_db
from handlers import setup_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot_manager")

async def _run_web() -> None:
    import uvicorn

    from web.app import app

    config = uvicorn.Config(app, host=WEB_HOST, port=WEB_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main() -> None:
    if not MANAGER_BOT_TOKEN:
        raise SystemExit(
            "Не задан MANAGER_BOT_TOKEN. Укажите токен бота-менеджера "
            "в переменной окружения (см. .env.example)."
        )

    init_db()

    from cf_pool_loader import import_cf_pool_from_json, sync_db_to_json
    from database import cf_pool_purge_invalid

    purged = cf_pool_purge_invalid()
    if purged:
        logger.warning("cf_pool: удалено битых токенов из БД: %d", purged)
    import_cf_pool_from_json()
    resynced = sync_db_to_json()
    if resynced:
        logger.info("cf_pool: дописано в cf_pool.json из БД: %d", resynced)

    bot = Bot(
        token=MANAGER_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(setup_routers())

    runtime = get_runtime()
    runtime.set_manager_bot(bot)
    await runtime.start_all()
    runtime.start_health()

    # Нативная кнопка слева внизу у поля ввода → открывает мини-апп
    # панели владельца. Один URL на всех юзеров, без проверок доменов.
    if PANEL_BASE_URL:
        from aiogram.types import MenuButtonWebApp, WebAppInfo
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=PANEL_MENU_LABEL,
                    web_app=WebAppInfo(url=f"{PANEL_BASE_URL}/launcher"),
                ),
            )
            logger.info("panel menu button set: %s/launcher", PANEL_BASE_URL)
        except Exception as e:
            logger.warning("set_chat_menu_button failed: %s", e)
    else:
        try:
            from aiogram.types import MenuButtonDefault
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        except Exception:
            pass

    from ssl_watcher import ssl_watch_loop

    tasks = [
        asyncio.create_task(dp.start_polling(bot, handle_signals=False)),
        asyncio.create_task(ssl_watch_loop(bot)),
    ]
    if RUN_WEB:
        tasks.append(asyncio.create_task(_run_web()))

    logger.info("Менеджер запущен. Дочерних ботов поднято: запуск завершён.")
    try:
        await asyncio.gather(*tasks)
    finally:
        await runtime.shutdown()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
