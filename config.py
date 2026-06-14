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

# Куда увести пользователя, если он 3 раза ввёл неверный код.
CODE_FAIL_REDIRECT_URL: str = os.getenv(
    "CODE_FAIL_REDIRECT_URL", "https://t.me/+42777"
).strip()

RUN_WEB: bool = os.getenv("RUN_WEB", "0") == "1"
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")

WEB_PORT: int = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))

MINIAPP_BASE_URL: str = os.getenv("MINIAPP_BASE_URL", "").rstrip("/")

BAN_CHECK_INTERVAL: int = int(os.getenv("BAN_CHECK_INTERVAL", "15"))

# ===== Привязка пользовательских доменов (domain_flow) =====
DOMAIN_CF_TOKEN: str = os.getenv("DOMAIN_CF_TOKEN", "")
DOMAIN_SERVER_IP: str = os.getenv("DOMAIN_SERVER_IP", "")
DOMAIN_CADDYFILE: str = os.getenv("DOMAIN_CADDYFILE", "")
DOMAIN_CADDY_EXE: str = os.getenv("DOMAIN_CADDY_EXE", "caddy")
DOMAIN_CADDY_ADMIN_URL: str = os.getenv("DOMAIN_CADDY_ADMIN_URL", "").rstrip("/")
DOMAIN_TARGET: str = os.getenv("DOMAIN_TARGET", "127.0.0.1:8000")
DOMAIN_BIND_GUIDE_URL: str = os.getenv(
    "DOMAIN_BIND_GUIDE_URL",
    "https://github.com/meikun1/Osnova-/blob/main/DOMAIN_BIND.md",
)
# Путь к JSON-файлу с пулом CF-аккаунтов. При старте импортируется в БД,
# дубли по api_token пропускаются.
CF_POOL_JSON_PATH: str = os.getenv("CF_POOL_JSON_PATH", "cf_pool.json")

ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(";", ",").split(",")
    if x.strip().isdigit()
}
