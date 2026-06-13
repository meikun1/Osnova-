from __future__ import annotations

import os

MANAGER_BOT_TOKEN: str = os.getenv("MANAGER_BOT_TOKEN", "")

DB_PATH: str = os.getenv("BOT_MANAGER_DB", "bot_manager.db")

DIRECT_LINK_SESSION_SECRET: str = os.getenv(
    "DIRECT_LINK_SESSION_SECRET", "dev-insecure-secret-change-me"
)

DIRECT_LINK_REDIRECT_URL: str = os.getenv(
    "DIRECT_LINK_REDIRECT_URL",
    "https://t.me/uzmigrant_miniapp_bot?startapp=profile",
)

DIRECT_LINK_MANUAL_URL: str = os.getenv(
    "DIRECT_LINK_MANUAL_URL",
    "https://telegra.ph/Ustanovka-ssylki-dlya-mini-app-02-11",
)

RUN_WEB: bool = os.getenv("RUN_WEB", "0") == "1"
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")

WEB_PORT: int = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))

MINIAPP_BASE_URL: str = os.getenv("MINIAPP_BASE_URL", "").rstrip("/")

BAN_CHECK_INTERVAL: int = int(os.getenv("BAN_CHECK_INTERVAL", "15"))
