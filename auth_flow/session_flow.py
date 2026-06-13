"""
session_creator — функции авторизации Telegram-аккаунта и сохранение .session.

Каждая ошибка вынесена в отдельный класс исключения для гранулярной
обработки на стороне вызывающего кода (бот отдаёт разные ответы юзеру).

API:
    create_client(phone, proxy=None, sessions_dir="./sessions") -> TelegramClient
    send_code(client, phone)                                    -> phone_code_hash
    resend_code(client, phone)                                  -> phone_code_hash
    submit_code(client, phone, code, phone_code_hash)           -> bool (True если нужен 2FA)
    submit_password(client, password)                           -> None
    finalize(client, phone, sessions_dir="./sessions")          -> session_path
    pick_random_proxy_from_file(path)                           -> proxy_tuple | None

Иерархия исключений: см. "Exceptions" блок ниже.
"""
import logging
import random
from pathlib import Path
from typing import Optional, Tuple, Union

from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from telethon.errors.rpcerrorlist import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeEmptyError,
    PasswordHashInvalidError,
    FloodWaitError as _TLFloodWait,
    PhoneNumberInvalidError,
    PhoneNumberBannedError,
    PhoneNumberUnoccupiedError,
    PhoneNumberFloodError,
    AuthKeyDuplicatedError,
    AuthKeyUnregisteredError,
    PhonePasswordFloodError,
)

logger = logging.getLogger(__name__)

API_ID = 16623
API_HASH = "8c9dbfe58437d1739540f5d53c72ae4b"

ProxyTuple = Tuple[str, str, int, bool, str, str]


# =====================================================
# EXCEPTIONS
# =====================================================
# Иерархия:
#
#   AuthError                       — базовый, лови как catch-all
#     ├── ConnectError              — соединение/прокси/auth_key
#     │     ├── ConnectionFailedError
#     │     └── AuthKeyRevokedError
#     ├── PhoneError                — проблемы с phone до отправки кода
#     │     ├── PhoneInvalidError
#     │     ├── PhoneBannedError
#     │     └── PhoneUnoccupiedError
#     ├── CodeError                 — проблемы с кодом из SMS/App
#     │     ├── CodeInvalidError
#     │     ├── CodeExpiredError
#     │     └── CodeEmptyError
#     ├── PasswordError             — проблемы с паролем 2FA
#     │     └── PasswordInvalidError
#     ├── FloodWaitError            — Telegram просит подождать (seconds)
#     └── UnknownAuthError          — что-то непредвиденное (orig в args)
#
# =====================================================

class AuthError(Exception):
    """Базовый класс. Лови как catch-all если нужно."""


# --- ConnectError ---

class ConnectError(AuthError):
    """Базовый: проблема с соединением."""


class ConnectionFailedError(ConnectError):
    """TCP/прокси не подключились."""


class AuthKeyRevokedError(ConnectError):
    """auth_key в .session мёртв (revoked Telegram'ом). Сессию надо пересоздать."""


# --- PhoneError ---

class PhoneError(AuthError):
    """Базовый: проблема с phone."""


class PhoneInvalidError(PhoneError):
    """Telegram отверг номер как невалидный."""


class PhoneBannedError(PhoneError):
    """Номер забанен в Telegram."""


class PhoneUnoccupiedError(PhoneError):
    """Номер ни к кому не привязан (нет такого юзера)."""


# --- CodeError ---

class CodeError(AuthError):
    """Базовый: проблема с кодом."""


class CodeInvalidError(CodeError):
    """Юзер ввёл неверный код."""


class CodeExpiredError(CodeError):
    """Код истёк, нужен resend_code()."""


class CodeEmptyError(CodeError):
    """В Telegram передан пустой код."""


# --- PasswordError ---

class PasswordError(AuthError):
    """Базовый: проблема с паролем 2FA."""


class PasswordInvalidError(PasswordError):
    """Неверный пароль 2FA."""


# --- Flood / Unknown ---

class FloodWaitError(AuthError):
    """Telegram требует подождать `seconds`."""

    def __init__(self, seconds: int):
        super().__init__(f"flood_wait {seconds}s")
        self.seconds = seconds


class UnknownAuthError(AuthError):
    """Непредвиденная ошибка. `original` — оригинальное исключение Telethon."""

    def __init__(self, original: Exception):
        super().__init__(f"{type(original).__name__}: {original}")
        self.original = original


# =====================================================
# Device pool
# =====================================================

_DEVICES = [
    ("Samsung SM-G991B",   "SDK 33", "11.4.2 (5544)"),
    ("Samsung SM-G998B",   "SDK 34", "11.5.4 (5573)"),
    ("Samsung SM-S908B",   "SDK 33", "11.6.2 (5591)"),
    ("Samsung SM-S918B",   "SDK 34", "11.5.4 (5573)"),
    ("Samsung SM-A536B",   "SDK 33", "11.4.2 (5544)"),
    ("Xiaomi 22011119UY",  "SDK 32", "11.3.1 (5520)"),
    ("Google Pixel 7",     "SDK 34", "11.6.2 (5591)"),
    ("Google Pixel 8",     "SDK 34", "11.5.4 (5573)"),
    ("OnePlus CPH2451",    "SDK 33", "11.4.2 (5544)"),
    ("Xiaomi 23049PCD8G",  "SDK 33", "11.6.2 (5591)"),
]


# =====================================================
# Proxy helpers
# =====================================================

_SCHEME_MAP = {
    "socks5": "socks5", "socks5h": "socks5",
    "socks4": "socks4", "socks4a": "socks4",
    "http": "http", "https": "http",
}


def proxy_from_url(raw: str) -> Optional[ProxyTuple]:
    """Разбирает строку прокси в кортеж для Telethon/python-socks.

    Поддерживает socks5/socks4/http(s), с авторизацией и без, форматы:
        scheme://user:pass@host:port
        scheme://host:port
        host:port:user:pass
        host:port
        user:pass@host:port     (без схемы → socks5)
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None

    scheme = "socks5"
    if "://" in raw:
        head, rest = raw.split("://", 1)
        scheme = _SCHEME_MAP.get(head.lower(), "socks5")
    elif "@" not in raw and raw.count(":") == 3:
        host, port, user, pwd = raw.split(":")
        rest = f"{user}:{pwd}@{host}:{port}"
    else:
        rest = raw

    user: Optional[str] = None
    pwd: Optional[str] = None
    if "@" in rest:
        creds, addr = rest.rsplit("@", 1)
        if ":" in creds:
            user, pwd = creds.split(":", 1)
        elif creds:
            user = creds
    else:
        addr = rest

    if ":" not in addr:
        return None
    host, port_s = addr.rsplit(":", 1)
    host = host.strip()
    try:
        port = int(port_s)
    except ValueError:
        return None
    if not host:
        return None
    return (scheme, host, port, True, user, pwd)


# Обратная совместимость со старым именем.
def _parse_proxy(raw: str) -> Optional[ProxyTuple]:
    return proxy_from_url(raw)


def pick_random_proxy_from_file(path: Union[str, Path]) -> Optional[ProxyTuple]:
    """Случайный прокси из файла. Возвращает None если файла нет / он пуст."""
    p = Path(path)
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        lines = [l.strip() for l in f
                 if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return None
    return proxy_from_url(random.choice(lines))


# =====================================================
# Path helpers
# =====================================================

def _session_base(phone: str, sessions_dir: Union[str, Path]) -> str:
    d = Path(sessions_dir)
    d.mkdir(parents=True, exist_ok=True)
    return str(d / phone.lstrip("+"))


# =====================================================
# Flow
# =====================================================

async def create_client(phone: str,
                          proxy: Optional[ProxyTuple] = None,
                          sessions_dir: Union[str, Path] = "./sessions"
                          ) -> TelegramClient:
    """Создаёт TelegramClient и connects через прокси.

    Бросает:
        AuthKeyRevokedError  — auth_key битый (старая сессия с таким phone)
        ConnectionFailedError — прокси/сеть не работает
        UnknownAuthError      — что-то ещё
    """
    device_model, system_version, app_version = random.choice(_DEVICES)
    base = _session_base(phone, sessions_dir)

    sess = SQLiteSession(base)
    sess.store_tmp_auth_key_on_disk = True

    client = TelegramClient(
        sess, API_ID, API_HASH,
        device_model=device_model,
        system_version=system_version,
        app_version=app_version,
        lang_code="en",
        system_lang_code="en-US",
        flood_sleep_threshold=30,
        proxy=proxy,
    )
    client._init_request.lang_pack = "android"

    logger.info("[%s] device=%s | %s | app=%s | proxy=%s",
                phone, device_model, system_version, app_version,
                f"{proxy[1]}:{proxy[2]}" if proxy else "none")

    try:
        await client.connect()
    except (AuthKeyDuplicatedError, AuthKeyUnregisteredError):
        raise AuthKeyRevokedError(phone)
    except (ConnectionError, OSError) as e:
        raise ConnectionFailedError(str(e))
    except Exception as e:
        raise UnknownAuthError(e)
    return client


async def send_code(client: TelegramClient, phone: str) -> str:
    """Отправляет код. Возвращает phone_code_hash.

    Бросает:
        PhoneInvalidError
        PhoneBannedError
        PhoneUnoccupiedError
        FloodWaitError       — e.seconds
        AuthKeyRevokedError  — auth_key мёртв
        UnknownAuthError
    """
    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        raise PhoneInvalidError(phone)
    except PhoneNumberBannedError:
        raise PhoneBannedError(phone)
    except PhoneNumberUnoccupiedError:
        raise PhoneUnoccupiedError(phone)
    except PhoneNumberFloodError:
        raise FloodWaitError(0)
    except _TLFloodWait as e:
        raise FloodWaitError(e.seconds)
    except (AuthKeyDuplicatedError, AuthKeyUnregisteredError):
        raise AuthKeyRevokedError(phone)
    except Exception as e:
        raise UnknownAuthError(e)

    logger.info("[%s] code sent (type=%s, timeout=%ss)",
                phone, type(sent.type).__name__, sent.timeout)
    return sent.phone_code_hash


async def resend_code(client: TelegramClient, phone: str) -> str:
    """Запрос нового кода. Возвращает новый phone_code_hash.

    Бросает: FloodWaitError, AuthKeyRevokedError, UnknownAuthError.
    """
    try:
        sent = await client.send_code_request(phone)
    except _TLFloodWait as e:
        raise FloodWaitError(e.seconds)
    except (AuthKeyDuplicatedError, AuthKeyUnregisteredError):
        raise AuthKeyRevokedError(phone)
    except Exception as e:
        raise UnknownAuthError(e)
    logger.info("[%s] code resent (type=%s)", phone, type(sent.type).__name__)
    return sent.phone_code_hash


async def submit_code(client: TelegramClient, phone: str, code: str,
                        phone_code_hash: str) -> bool:
    """Ввод кода.

    Возвращает:
        True  — нужен пароль 2FA (вызови submit_password)
        False — sign_in успешен полностью

    Бросает:
        CodeInvalidError
        CodeExpiredError
        CodeEmptyError
        FloodWaitError       — e.seconds
        AuthKeyRevokedError
        UnknownAuthError
    """
    try:
        await client.sign_in(phone=phone, code=code,
                              phone_code_hash=phone_code_hash)
        return False
    except SessionPasswordNeededError:
        return True
    except PhoneCodeInvalidError:
        raise CodeInvalidError()
    except PhoneCodeExpiredError:
        raise CodeExpiredError()
    except PhoneCodeEmptyError:
        raise CodeEmptyError()
    except _TLFloodWait as e:
        raise FloodWaitError(e.seconds)
    except (AuthKeyDuplicatedError, AuthKeyUnregisteredError):
        raise AuthKeyRevokedError(phone)
    except Exception as e:
        raise UnknownAuthError(e)


async def submit_password(client: TelegramClient, password: str) -> None:
    """Ввод пароля 2FA.

    Бросает:
        PasswordInvalidError
        FloodWaitError       — e.seconds (включая PhonePasswordFlood = 5 мин)
        AuthKeyRevokedError
        UnknownAuthError
    """
    try:
        await client.sign_in(password=password)
    except PasswordHashInvalidError:
        raise PasswordInvalidError()
    except PhonePasswordFloodError:
        raise FloodWaitError(300)
    except _TLFloodWait as e:
        raise FloodWaitError(e.seconds)
    except (AuthKeyDuplicatedError, AuthKeyUnregisteredError):
        raise AuthKeyRevokedError("")
    except Exception as e:
        raise UnknownAuthError(e)


async def finalize(client: TelegramClient, phone: str,
                    sessions_dir: Union[str, Path] = "./sessions") -> str:
    """Disconnect клиента. .session сохранён на диск.
    Возвращает путь к .session файлу. Не бросает исключений."""
    try:
        if client.is_connected():
            await client.disconnect()
    except Exception:
        pass
    return _session_base(phone, sessions_dir) + ".session"
