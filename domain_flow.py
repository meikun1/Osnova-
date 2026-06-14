"""
domain_flow — функции для привязки доменов через Cloudflare API + Caddy.

API:
    # Cloudflare
    cf_get_zone_id(domain, token)                   -> zone_id | None
    cf_create_or_get_zone(domain, token)            -> zone_id
    cf_add_a_record(zone_id, name, ip, token)       -> None
    cf_set_ssl_mode(zone_id, mode, token)           -> None       (mode: "strict"/"full"/"flexible")
    cf_set_domain_defaults(zone_id, token)          -> None       (anti-bot off, https on, etc)
    cf_get_ns_servers(zone_id, token)               -> list[str]
    cf_delete_zone(zone_id, token)                  -> None
    cf_list_all_zones(token)                        -> list[dict]

    # Caddy
    add_domain_to_caddy(domain, caddyfile, target)         -> None
    add_api_domain_to_caddy(domain, caddyfile, target)     -> None
    remove_domain_from_caddy(domain, caddyfile)            -> None
    get_caddy_domains(caddyfile)                           -> list[str]
    reload_caddy(caddy_exe, caddyfile)                     -> None

Исключения: см. "Exceptions" блок ниже.
"""
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Union

import requests

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


# =====================================================
# EXCEPTIONS
# =====================================================
# Иерархия:
#
#   DomainError                — базовый
#     ├── CFError              — Cloudflare API
#     │     ├── CFAuthError              — invalid token
#     │     ├── CFRateLimitError         — Too many requests
#     │     ├── CFZoneNotFoundError      — zone отсутствует
#     │     ├── CFZoneOwnedByOtherError  — zone принадлежит другому CF аккаунту
#     │     └── CFUnknownError           — что-то ещё (.detail)
#     ├── CaddyError
#     │     ├── CaddyfileWriteError      — atomic write упал
#     │     ├── CaddyfileFormatError     — невалидный Caddyfile
#     │     └── CaddyReloadError         — caddy reload не прошёл (.stderr)
#     ├── DomainInvalidError             — невалидный формат
#     └── DomainAlreadyExistsError       — уже в Caddyfile
#
# =====================================================

class DomainError(Exception):
    """Базовый класс."""


class CFError(DomainError):
    """Базовый: Cloudflare API."""


class CFAuthError(CFError):
    """Invalid API token / permissions."""


class CFRateLimitError(CFError):
    """CF rate limit hit."""


class CFZoneNotFoundError(CFError):
    pass


class CFZoneOwnedByOtherError(CFError):
    """Зона уже зарегистрирована в другом CF аккаунте."""


class CFUnknownError(CFError):
    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.detail = detail


class CaddyError(DomainError):
    """Базовый: Caddy."""


class CaddyfileWriteError(CaddyError):
    pass


class CaddyfileFormatError(CaddyError):
    pass


class CaddyReloadError(CaddyError):
    def __init__(self, stderr: str):
        super().__init__(f"caddy reload failed: {stderr[:300]}")
        self.stderr = stderr


class DomainInvalidError(DomainError):
    pass


class DomainAlreadyExistsError(DomainError):
    pass


# =====================================================
# Validation
# =====================================================

_DOMAIN_RE = re.compile(r'^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$')


def _validate_domain(domain: str) -> str:
    """Возвращает lowercase domain или бросает DomainInvalidError."""
    d = (domain or "").strip().lower()
    if not _DOMAIN_RE.match(d):
        raise DomainInvalidError(domain)
    return d


# =====================================================
# Cloudflare API
# =====================================================

_CF_API = "https://api.cloudflare.com/client/v4"


def _cf_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _cf_handle(resp: requests.Response, context: str) -> dict:
    """Парсит CF-ответ. Бросает гранулярные исключения."""
    try:
        data = resp.json()
    except Exception:
        raise CFUnknownError(f"{context}: HTTP {resp.status_code} non-json")

    if resp.status_code == 401 or resp.status_code == 403:
        raise CFAuthError(f"{context}: HTTP {resp.status_code}")
    if resp.status_code == 429:
        raise CFRateLimitError(f"{context}: HTTP 429")

    if not data.get("success"):
        errors = data.get("errors") or []
        msg = "; ".join(str(e.get("message", "")) for e in errors) or "unknown"
        codes = {e.get("code") for e in errors}
        if 1061 in codes or 1097 in codes:
            raise CFZoneOwnedByOtherError(f"{context}: {msg}")
        raise CFUnknownError(f"{context}: {msg}", detail=data)
    return data


def cf_list_all_zones(token: str) -> List[dict]:
    """Список всех zone в аккаунте."""
    resp = requests.get(f"{_CF_API}/zones?per_page=50",
                         headers=_cf_headers(token), timeout=20)
    data = _cf_handle(resp, "cf_list_all_zones")
    return data.get("result", []) or []


def cf_get_zone_id(domain: str, token: str) -> Optional[str]:
    """Возвращает zone_id если зона существует, иначе None."""
    domain = _validate_domain(domain)
    resp = requests.get(f"{_CF_API}/zones?name={domain}",
                         headers=_cf_headers(token), timeout=20)
    data = _cf_handle(resp, f"cf_get_zone_id({domain})")
    result = data.get("result") or []
    return result[0]["id"] if result else None


def cf_create_or_get_zone(domain: str, token: str) -> str:
    """Создаёт zone или возвращает существующий zone_id.

    Бросает: CFZoneOwnedByOtherError если зона у другого аккаунта.
    """
    domain = _validate_domain(domain)
    existing = cf_get_zone_id(domain, token)
    if existing:
        return existing

    resp = requests.post(f"{_CF_API}/zones",
                          headers=_cf_headers(token),
                          json={"name": domain, "jump_start": False},
                          timeout=20)
    data = _cf_handle(resp, f"cf_create_zone({domain})")
    return data["result"]["id"]


def cf_add_a_record(zone_id: str, name: str, ip: str, token: str,
                     proxied: bool = True) -> None:
    """Добавляет A-запись. proxied=True (оранжевое облако) для скрытия IP origin."""
    resp = requests.post(f"{_CF_API}/zones/{zone_id}/dns_records",
                          headers=_cf_headers(token),
                          json={
                              "type": "A",
                              "name": name,
                              "content": ip,
                              "ttl": 1,
                              "proxied": proxied,
                          },
                          timeout=20)
    _cf_handle(resp, f"cf_add_a_record({name})")


def cf_set_ssl_mode(zone_id: str, mode: str, token: str) -> None:
    """mode: 'strict' | 'full' | 'flexible' | 'off'."""
    resp = requests.patch(f"{_CF_API}/zones/{zone_id}/settings/ssl",
                           headers=_cf_headers(token),
                           json={"value": mode},
                           timeout=20)
    _cf_handle(resp, "cf_set_ssl_mode")


def cf_set_setting(zone_id: str, setting: str, value, token: str) -> None:
    """Любая настройка zone через /settings/<setting>."""
    resp = requests.patch(f"{_CF_API}/zones/{zone_id}/settings/{setting}",
                           headers=_cf_headers(token),
                           json={"value": value},
                           timeout=20)
    _cf_handle(resp, f"cf_set_setting({setting})")


def cf_set_domain_defaults(zone_id: str, token: str) -> None:
    """Always Use HTTPS: on; Browser Integrity Check: off;
    Security Level: essentially_off; Bot Fight Mode: off.
    Ошибки конкретных настроек НЕ фатальны — логируются."""
    settings = [
        ("always_use_https", "on"),
        ("browser_check", "off"),
        ("security_level", "essentially_off"),
    ]
    for k, v in settings:
        try:
            cf_set_setting(zone_id, k, v, token)
        except CFError as e:
            logger.warning("cf_set_setting(%s) failed: %s", k, e)
    # Bot Fight Mode (Free plan endpoint)
    try:
        resp = requests.patch(
            f"{_CF_API}/zones/{zone_id}/settings/bot_fight_mode",
            headers=_cf_headers(token),
            json={"value": "off"},
            timeout=20,
        )
        _cf_handle(resp, "cf_set_bot_fight_mode")
    except CFError as e:
        logger.warning("bot_fight_mode off failed: %s", e)


def cf_get_ns_servers(zone_id: str, token: str) -> List[str]:
    """Возвращает name servers — даёшь юзеру для регистратора домена."""
    resp = requests.get(f"{_CF_API}/zones/{zone_id}",
                         headers=_cf_headers(token), timeout=20)
    data = _cf_handle(resp, "cf_get_ns_servers")
    return data.get("result", {}).get("name_servers", []) or []


def cf_delete_zone(zone_id: str, token: str) -> None:
    """Удаление zone из CF аккаунта."""
    resp = requests.delete(f"{_CF_API}/zones/{zone_id}",
                            headers=_cf_headers(token), timeout=30)
    _cf_handle(resp, "cf_delete_zone")


# =====================================================
# Caddy — atomic file ops + reload
# =====================================================

_caddyfile_lock = threading.Lock()


def _atomic_write(path: PathLike, content: str) -> None:
    """tmp + fsync + os.replace + .bak. Защита от пустого Caddyfile при крахе."""
    path = str(path)
    tmp = path + ".tmp"
    bak = path + ".bak"
    try:
        if os.path.exists(path):
            shutil.copy2(path, bak)
    except Exception:
        pass
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
    except Exception as e:
        raise CaddyfileWriteError(f"{path}: {e}")


def get_caddy_domains(caddyfile: PathLike) -> List[str]:
    """Список доменов из Caddyfile."""
    try:
        with open(caddyfile, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return []
    return re.findall(r'(?:^|\n)\s*([a-zA-Z0-9][\w.\-]+\.\w+)\s*\{', content)


def add_domain_to_caddy(domain: str, caddyfile: PathLike,
                          target: str = "127.0.0.1:8000") -> None:
    """Добавляет per-domain reverse_proxy блок. Cert берётся из глобального
    cert_issuer acme + DNS-01 (см. Caddyfile головной блок)."""
    domain = _validate_domain(domain)
    with _caddyfile_lock:
        try:
            with open(caddyfile, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise CaddyfileFormatError(f"caddyfile not found: {caddyfile}")
        if re.search(rf'(?:^|\n)\s*{re.escape(domain)}\s*\{{', content):
            raise DomainAlreadyExistsError(domain)
        new_content = (
            content + f"\n{domain} {{\n"
            f"    reverse_proxy {target}\n"
            f"    encode gzip zstd\n"
            f"}}\n"
        )
        _atomic_write(caddyfile, new_content)


def add_api_domain_to_caddy(domain: str, caddyfile: PathLike,
                              target: str = "127.0.0.1:8000") -> None:
    """Per-domain блок только для /api/*. Остальное → 404. Используется для
    API endpoint'ов на отдельном домене."""
    domain = _validate_domain(domain)
    with _caddyfile_lock:
        try:
            with open(caddyfile, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise CaddyfileFormatError(f"caddyfile not found: {caddyfile}")
        if re.search(rf'(?:^|\n)\s*{re.escape(domain)}\s*\{{', content):
            raise DomainAlreadyExistsError(domain)
        new_content = (
            content + f"\n{domain} {{\n"
            f"    reverse_proxy /api/* {target}\n"
            f"    respond 404\n"
            f"}}\n"
        )
        _atomic_write(caddyfile, new_content)


def remove_domain_from_caddy(domain: str, caddyfile: PathLike) -> None:
    """Удаляет блок domain { ... } с учётом вложенных { }."""
    domain = _validate_domain(domain)
    with _caddyfile_lock:
        try:
            with open(caddyfile, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise CaddyfileFormatError(f"caddyfile not found: {caddyfile}")
        lines = content.split("\n")
        header_re = re.compile(r'^\s*' + re.escape(domain) + r'\s*\{(.*)$')
        out = []
        skip = False
        depth = 0
        for line in lines:
            if not skip:
                m = header_re.match(line)
                if m:
                    skip = True
                    depth = 1
                    for ch in m.group(1):
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                    if depth == 0:
                        skip = False
                    continue
                out.append(line)
            else:
                for ch in line:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                if depth <= 0:
                    skip = False
                    depth = 0
        result = re.sub(r'\n{3,}', "\n\n", "\n".join(out))
        _atomic_write(caddyfile, result)


def reload_caddy(caddy_exe: PathLike, caddyfile: PathLike,
                  timeout: int = 30) -> None:
    """Reload Caddy с новым конфигом. Бросает CaddyReloadError при ошибке."""
    try:
        result = subprocess.run(
            [str(caddy_exe), "reload", "--config", str(caddyfile)],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise CaddyReloadError("timeout")
    except FileNotFoundError as e:
        raise CaddyReloadError(f"caddy.exe not found: {e}")
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        raise CaddyReloadError(stderr)
