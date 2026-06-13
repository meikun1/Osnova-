"""Проверка прокси и определение гео по выходному IP.

Запрос делается *через сам прокси* — так мы одновременно убеждаемся, что
прокси рабочий, и узнаём страну выходного IP (которую видит Telegram).
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ip-api: бесплатный, без ключа, только http на free-тарифе.
_GEO_URL = "http://ip-api.com/json/?fields=status,country,countryCode,query"


def country_flag(cc: Optional[str]) -> str:
    """ISO-код страны → эмодзи-флаг ('DE' → 🇩🇪). Пусто, если код кривой."""
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)


async def check_proxy(url: str, timeout: float = 12.0) -> Tuple[bool, Optional[str]]:
    """Проверяет прокси, обращаясь через него к ip-api.

    Возвращает (работает, гео). `гео` — строка вида "🇩🇪 Germany" либо None,
    если запрос прошёл, но страну определить не удалось.
    """
    if not url:
        return (False, None)
    try:
        import aiohttp
        from aiohttp_socks import ProxyConnector
    except Exception as e:  # зависимостей нет — не валим бота
        logger.warning("proxy check deps missing: %s", e)
        return (False, None)

    try:
        connector = ProxyConnector.from_url(url)
    except Exception as e:
        logger.info("proxy url parse failed (%s): %s", url, e)
        return (False, None)

    try:
        async with aiohttp.ClientSession(connector=connector) as sess:
            async with sess.get(
                _GEO_URL, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as r:
                data = await r.json()
    except Exception as e:
        logger.info("proxy check failed (%s): %s", url, e)
        return (False, None)

    if not isinstance(data, dict) or data.get("status") != "success":
        return (True, None)  # прокси ответил, но гео неизвестно

    country = data.get("country")
    cc = data.get("countryCode")
    flag = country_flag(cc)
    if country and flag:
        geo = f"{flag} {country}"
    elif country:
        geo = country
    else:
        geo = cc or None
    return (True, geo)


def _scheme_variants(url: str) -> list:
    """Пробуем указанную схему, затем альтернативную (http ↔ socks5)."""
    variants = [url]
    low = url.lower()
    if low.startswith("http://"):
        variants.append("socks5://" + url[len("http://"):])
    elif low.startswith("https://"):
        variants.append("socks5://" + url[len("https://"):])
    elif low.startswith("socks5://"):
        variants.append("http://" + url[len("socks5://"):])
    elif low.startswith("socks4://"):
        variants.append("http://" + url[len("socks4://"):])
    return variants


async def check_proxy_smart(url: str, timeout: float = 12.0):
    """Как check_proxy, но если схема не подошла — пробует http/socks5.

    Возвращает (работает, гео, рабочий_url). Рабочий url может отличаться
    от исходного, если подошла альтернативная схема.
    """
    for cand in _scheme_variants(url):
        ok, geo = await check_proxy(cand, timeout)
        if ok:
            return (True, geo, cand)
    return (False, None, url)
