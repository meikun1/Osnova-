from aiogram import Router

from handlers import (
    add_settings,
    broadcast,
    create_bot,
    direct_link,
    export_sessions,
    folders,
    guard,
    health,
    manage_bots,
    proxy,
    restart,
    settings,
    start,
    statistics,
    template,
    token_broadcast,
)

def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(health.router)
    root.include_router(create_bot.router)
    root.include_router(manage_bots.router)
    root.include_router(restart.router)
    root.include_router(guard.router)
    root.include_router(statistics.router)
    root.include_router(template.router)
    root.include_router(settings.router)
    root.include_router(proxy.router)
    root.include_router(direct_link.router)
    root.include_router(broadcast.router)
    root.include_router(add_settings.router)
    root.include_router(token_broadcast.router)
    root.include_router(folders.router)
    root.include_router(export_sessions.router)
    return root
