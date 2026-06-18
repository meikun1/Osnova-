"""Фоновая задача: пингует ещё не уведомлённые домены, и как только на :443
поднимется валидный SSL-сертификат — шлёт юзеру уведомление и помечает домен
в БД (ssl_notified=1)."""
from __future__ import annotations

import asyncio
import logging
import socket
import ssl
from datetime import datetime, timezone

from aiogram import Bot

from database import (
    user_domain_mark_ssl_notified,
    user_domains_pending_ssl,
)

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 5 * 60        # секунд между прогонами
PROBE_TIMEOUT = 6              # таймаут одного TLS-handshake


def _probe_ssl(domain: str) -> bool:
    """True если на domain:443 уже отдают валидный сертификат.
    IDN-домены конвертируем в ASCII (Punycode), пробуем 2 раза
    (первый коннект через CF иногда падает по таймауту)."""
    try:
        host = domain.encode("idna").decode("ascii")
    except Exception:
        host = domain
    ctx = ssl.create_default_context()
    for attempt in range(2):
        try:
            with socket.create_connection((host, 443), timeout=PROBE_TIMEOUT) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    if not cert:
                        continue
                    not_after = cert.get("notAfter")
                    if not_after:
                        exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                        if exp.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                            continue
                    return True
        except Exception:
            if attempt == 0:
                continue
            return False
    return False


async def _notify(bot: Bot, user_id: int, domain: str) -> None:
    text = (
        f"🔒 <b>SSL-сертификат выпущен</b>\n\n"
        f"Домен <code>{domain}</code> готов — можно открывать "
        f"<a href=\"https://{domain}\">https://{domain}</a>."
    )
    await bot.send_message(user_id, text, disable_web_page_preview=True)


async def ssl_watch_loop(bot: Bot) -> None:
    """Бесконечный цикл. Запускается из bot.py после init_db()."""
    while True:
        try:
            pending = await asyncio.to_thread(user_domains_pending_ssl)
            for row in pending:
                domain = row["domain"]
                ok = await asyncio.to_thread(_probe_ssl, domain)
                if not ok:
                    continue
                try:
                    await _notify(bot, row["user_id"], domain)
                except Exception:
                    logger.exception("ssl notify failed for %s", domain)
                    continue
                await asyncio.to_thread(user_domain_mark_ssl_notified, row["id"])
        except Exception:
            logger.exception("ssl_watch_loop iteration crashed")
        await asyncio.sleep(CHECK_INTERVAL)
