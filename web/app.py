from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import CODE_FAIL_REDIRECT_URL
from database import (
    get_bot_by_tg_id,
    get_template,
    init_db,
    record_miniapp_launch,
)
from directlink_service import get_module
from miniapp_template import (
    ALL_DEFAULTS,
    DEFAULT_VIEW,
    PAGE_FIELDS,
    PAGES,
    background_css,
    page_field_key,
)

from web.auth_api import router as auth_router, start_gc

_MINIAPP_HTML = (Path(__file__).parent / "miniapp.html").read_text(encoding="utf-8")
_PREVIEW3D_HTML = (Path(__file__).parent / "preview3d.html").read_text(encoding="utf-8")
_PANEL_PATH = Path(__file__).parent / "panel.html"

def _miniapp_config(bot_id: int) -> dict:
    cfg: dict = {
        "color": "", "bg": "", "blur": 0, "view": DEFAULT_VIEW, "title": "",
        "pages": [], "codeFailRedirect": CODE_FAIL_REDIRECT_URL,
    }
    content: dict = {}
    bot = get_bot_by_tg_id(bot_id)
    if bot and bot.get("template_id"):
        t = get_template(bot["template_id"])
        if t:
            content = t["content"]
            # Берём только пользовательский app_name; имя шаблона ("Стандартный
            # шаблон") не используем как заголовок мини-аппа.
            cfg["title"] = (content.get("app_name") or "").strip()

    def _val(key: str) -> str:
        v = content.get(key)
        if v is not None and str(v).strip():
            return v
        return ALL_DEFAULTS.get(key, "")

    color = content.get("ui_color") or ""
    cfg["color"] = "" if color in ("", "default") else color
    cfg["bg"] = background_css(content.get("bg"))
    cfg["blur"] = int(content.get("blur") or 0)
    cfg["view"] = content.get("view") or DEFAULT_VIEW
    for page in PAGES:
        pdata = {"key": page}
        for field, _label in PAGE_FIELDS[page]:
            pdata[field] = _val(page_field_key(page, field))
        cfg["pages"].append(pdata)
    return cfg

def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="Bot Manager — Mini App")

    _model_dir = Path(__file__).parent / "model"
    if _model_dir.is_dir():
        app.mount("/model", StaticFiles(directory=str(_model_dir)), name="model")

    _static_dir = Path(__file__).parent / "static"
    if _static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.on_event("startup")
    async def _on_startup() -> None:
        start_gc()

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/3d", response_class=HTMLResponse)
    async def preview3d() -> HTMLResponse:
        return HTMLResponse(
            _PREVIEW3D_HTML,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/app/{bot_id}", response_class=HTMLResponse)
    async def mini_app(bot_id: int) -> HTMLResponse:
        try:
            record_miniapp_launch(bot_id)
        except Exception:
            pass
        cfg = _miniapp_config(bot_id)
        cfg_json = json.dumps(cfg, ensure_ascii=False).replace("<", "\\u003c")
        page = _MINIAPP_HTML.replace("__BOT_ID__", str(bot_id))
        page = page.replace("__CFG__", cfg_json)
        return HTMLResponse(
            page,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # авторизация Telegram-аккаунта
    app.include_router(auth_router)

    # панель владельца бота
    from web.panel_api import router as panel_router
    app.include_router(panel_router)

    _LAUNCHER_PATH = Path(__file__).parent / "launcher.html"
    _EVA_PATH = Path(__file__).parent / "eva.html"

    def _serve_static_html(path: Path) -> HTMLResponse:
        import os
        html = path.read_text(encoding="utf-8")
        mtime = int(os.path.getmtime(path))
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "ETag": f'"{mtime}"',
            },
        )

    @app.get("/launcher", response_class=HTMLResponse)
    async def launcher_page() -> HTMLResponse:
        return _serve_static_html(_LAUNCHER_PATH)

    @app.get("/eva", response_class=HTMLResponse)
    async def eva_page() -> HTMLResponse:
        return _serve_static_html(_EVA_PATH)

    @app.get("/panel", response_class=HTMLResponse)
    async def panel_page() -> HTMLResponse:
        # Читаем файл при каждом запросе — изменения подхватываются мгновенно
        # без рестарта контейнера. Плюс отдаём mtime как версию.
        import os
        html = _PANEL_PATH.read_text(encoding="utf-8")
        mtime = int(os.path.getmtime(_PANEL_PATH))
        # Cache-bust для template-render.js (его статика отдаётся StaticFiles
        # и Telegram WebView держит в кэше дольше, чем хотелось бы).
        tr_path = _PANEL_PATH.parent / "static" / "template-render.js"
        try:
            tr_v = int(os.path.getmtime(tr_path))
        except OSError:
            tr_v = mtime
        html = html.replace("__TR_V__", f"v={tr_v}")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "ETag": f'"{mtime}"',
                "X-Panel-Build": str(mtime),
            },
        )

    get_module().mount(app)
    return app

app = create_app()
