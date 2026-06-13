from __future__ import annotations

import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Awaitable, Callable

from fastapi import APIRouter, Cookie, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .config import DirectLinkConfig
from .storage import BotState, DirectLinkStorage
from .telegram import InitDataError, verify_init_data

GetBotToken = Callable[[int], Awaitable[str | None]]
GetBotUsername = Callable[[int], Awaitable[str | None]]
VerifyAdmin = Callable[[Request, int], Awaitable[None]]

class StartIn(BaseModel):
    init_data: str

    token: str | None = None

class StartOut(BaseModel):
    mode: str
    redirect_url: str | None = None

class SettingsOut(BaseModel):
    enabled: bool
    startapp_url: str
    manual_url: str

class ToggleIn(BaseModel):
    enabled: bool

class DirectLinkModule:
    def __init__(
        self,
        config: DirectLinkConfig,
        storage: DirectLinkStorage,
        get_bot_token: GetBotToken,
        get_bot_username: GetBotUsername,
        verify_admin: VerifyAdmin,
    ) -> None:
        self.config = config
        self.storage = storage
        self.get_bot_token = get_bot_token
        self.get_bot_username = get_bot_username
        self.verify_admin = verify_admin

    async def is_enabled_for(self, bot_id: int) -> bool:
        state = await self.storage.get(bot_id)
        return bool(state and state["enabled"])

    async def get_or_init(self, bot_id: int) -> BotState:
        state = await self.storage.get(bot_id)
        if state is None:
            state = await self.storage.init(bot_id, secrets.token_urlsafe(16))
        return state

    async def build_url(self, bot_id: int) -> str:
        state = await self.get_or_init(bot_id)
        username = await self.get_bot_username(bot_id)
        if not username:
            raise HTTPException(404, "bot username unknown")
        return f"https://t.me/{username}?startapp={state['startapp_token']}"

    def _make_cookie(self, bot_id: int, user_id: int, token_version: int) -> str:
        payload = {
            "b": bot_id,
            "u": user_id,
            "v": token_version,
            "e": int(time.time()) + self.config.session_max_age,
        }
        body = urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        sig = hmac.new(
            self.config.session_secret.encode(), body.encode(), "sha256"
        ).hexdigest()
        return f"{body}.{sig}"

    def _read_cookie(self, raw: str | None) -> dict | None:
        if not raw or "." not in raw:
            return None
        body, sig = raw.rsplit(".", 1)
        expected = hmac.new(
            self.config.session_secret.encode(), body.encode(), "sha256"
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        try:
            pad = "=" * (-len(body) % 4)
            payload = json.loads(urlsafe_b64decode(body + pad))
        except (ValueError, json.JSONDecodeError):
            return None
        if payload.get("e", 0) < int(time.time()):
            return None
        return payload

    def _set_cookie(self, response: Response, value: str) -> None:
        response.set_cookie(
            key=self.config.cookie_name,
            value=value,
            max_age=self.config.session_max_age,
            httponly=True,
            secure=True,
            samesite="none",
        )

    def _stub(self) -> StartOut:
        return StartOut(mode="stub", redirect_url=self.config.redirect_url)

    def build_router(self) -> APIRouter:
        router = APIRouter()
        cookie_name = self.config.cookie_name

        @router.post("/dl/{bot_id}/auth/start", response_model=StartOut)
        async def auth_start(
            bot_id: int, payload: StartIn, response: Response
        ) -> StartOut:
            state = await self.storage.get(bot_id)
            if state is None:
                return self._stub()

            bot_token = await self.get_bot_token(bot_id)
            if not bot_token:
                return self._stub()

            try:
                user, start_param = verify_init_data(
                    payload.init_data, bot_token, self.config.init_data_ttl
                )
            except InitDataError:
                return self._stub()

            if start_param:

                if not state["enabled"]:
                    return self._stub()
                provided = start_param
            else:

                provided = payload.token or ""

            if not provided or not hmac.compare_digest(
                provided, state["startapp_token"]
            ):
                return self._stub()

            cookie = self._make_cookie(bot_id, user.id, state["token_version"])
            self._set_cookie(response, cookie)
            return StartOut(mode="granted")

        @router.get("/dl/{bot_id}/auth/me", response_model=StartOut)
        async def auth_me(
            bot_id: int,
            token: str | None = Cookie(default=None, alias=cookie_name),
        ) -> StartOut:
            state = await self.storage.get(bot_id)
            if state is None:
                return self._stub()
            payload = self._read_cookie(token)
            if (
                payload is None
                or payload.get("b") != bot_id
                or payload.get("v") != state["token_version"]
            ):
                return self._stub()
            return StartOut(mode="granted")

        @router.get("/dl/admin/{bot_id}", response_model=SettingsOut)
        async def admin_get(bot_id: int, request: Request) -> SettingsOut:
            await self.verify_admin(request, bot_id)
            state = await self.get_or_init(bot_id)
            url = await self.build_url(bot_id)
            return SettingsOut(
                enabled=state["enabled"],
                startapp_url=url,
                manual_url=self.config.manual_url,
            )

        @router.post("/dl/admin/{bot_id}/toggle", response_model=SettingsOut)
        async def admin_toggle(
            bot_id: int, payload: ToggleIn, request: Request
        ) -> SettingsOut:
            await self.verify_admin(request, bot_id)
            await self.get_or_init(bot_id)
            await self.storage.set_enabled(bot_id, payload.enabled)
            state = await self.storage.get(bot_id)
            assert state is not None
            url = await self.build_url(bot_id)
            return SettingsOut(
                enabled=state["enabled"],
                startapp_url=url,
                manual_url=self.config.manual_url,
            )

        @router.post("/dl/admin/{bot_id}/rotate", response_model=SettingsOut)
        async def admin_rotate(bot_id: int, request: Request) -> SettingsOut:
            await self.verify_admin(request, bot_id)
            await self.get_or_init(bot_id)
            state = await self.storage.rotate_token(bot_id, secrets.token_urlsafe(16))
            url = await self.build_url(bot_id)
            return SettingsOut(
                enabled=state["enabled"],
                startapp_url=url,
                manual_url=self.config.manual_url,
            )

        return router

    def mount(self, app: FastAPI, prefix: str = "") -> None:
        app.include_router(self.build_router(), prefix=prefix)
