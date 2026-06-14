"""Привязка пользовательского домена через Cloudflare API + Caddy.

Запускается из главного меню кнопкой «🌐 Привязать свой домен».
"""
from __future__ import annotations

import asyncio
import html
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from database import cf_pool_get_for_user, cf_pool_stats, user_domain_add
from domain_flow import (
    CaddyReloadError,
    CFError,
    CFZoneOwnedByOtherError,
    DomainAlreadyExistsError,
    DomainInvalidError,
    add_domain_to_caddy_with_token,
    cf_add_a_record,
    cf_create_or_get_zone,
    cf_get_ns_servers,
    cf_set_domain_defaults,
    cf_set_ssl_mode,
    reload_caddy,
    remove_domain_from_caddy,
)

logger = logging.getLogger(__name__)

router = Router()


class DomainBind(StatesGroup):
    waiting_domain = State()


def _back_kb() -> InlineKeyboardMarkup:
    rows = []
    if config.DOMAIN_BIND_GUIDE_URL:
        rows.append([
            InlineKeyboardButton(
                text="📖 Инструкция", url=config.DOMAIN_BIND_GUIDE_URL
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _missing_config() -> list[str]:
    missing = []
    if not config.DOMAIN_SERVER_IP:
        missing.append("DOMAIN_SERVER_IP")
    if not config.DOMAIN_CADDYFILE:
        missing.append("DOMAIN_CADDYFILE")
    return missing


@router.callback_query(F.data == "domain_bind")
async def start_bind(callback: CallbackQuery, state: FSMContext) -> None:
    missing = _missing_config()
    if missing:
        await callback.message.edit_text(
            "🌐 <b>Привязка домена недоступна</b>\n\n"
            "Не заданы переменные окружения:\n<code>"
            + "\n".join(missing)
            + "</code>",
            reply_markup=_back_kb(),
        )
        await callback.answer()
        return

    await state.set_state(DomainBind.waiting_domain)
    await callback.message.edit_text(
        "🌐 <b>Привязка своего домена</b>\n\n"
        "Отправьте доменное имя (например <code>example.com</code>).\n\n"
        "Дальше бот сам:\n"
        "• создаст зону в Cloudflare,\n"
        "• добавит A-запись на сервер,\n"
        "• включит SSL Strict + анти-bot настройки,\n"
        "• пропишет блок в Caddy и сделает reload,\n"
        "• выдаст NS-серверы для регистратора.\n\n"
        "📖 Полная пошаговая инструкция — по кнопке ниже.",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@router.message(DomainBind.waiting_domain, F.text, ~F.text.startswith("/"))
async def receive_domain(message: Message, state: FSMContext) -> None:
    domain = (message.text or "").strip().lower()
    status = await message.answer(f"⏳ Обрабатываю <code>{html.escape(domain)}</code>…")

    account = cf_pool_get_for_user(message.from_user.id)
    if not account:
        stats = cf_pool_stats()
        await status.edit_text(
            "❌ В пуле нет свободных Cloudflare-аккаунтов.\n"
            f"Всего: {stats['total']}, занято: {stats['taken']}.\n\n"
            "Сообщите администратору — он добавит новые аккаунты в пул.",
            reply_markup=_back_kb(),
        )
        await state.clear()
        return

    try:
        ns_servers = await asyncio.to_thread(
            _bind_domain_sync, domain, account["api_token"]
        )
    except DomainInvalidError:
        await status.edit_text(
            "❌ Невалидный формат домена. Пример: <code>example.com</code>",
            reply_markup=_back_kb(),
        )
        return
    except CFZoneOwnedByOtherError:
        await status.edit_text(
            "❌ Этот домен уже зарегистрирован в другом Cloudflare-аккаунте.",
            reply_markup=_back_kb(),
        )
        await state.clear()
        return
    except DomainAlreadyExistsError:
        await status.edit_text(
            "ℹ️ Домен уже есть в Caddyfile.", reply_markup=_back_kb()
        )
        await state.clear()
        return
    except CaddyReloadError as e:
        await status.edit_text(
            f"❌ Caddy reload не прошёл:\n<code>{html.escape(e.stderr[:500])}</code>\n\n"
            "Блок в Caddyfile откатил.",
            reply_markup=_back_kb(),
        )
        await state.clear()
        return
    except CFError as e:
        await status.edit_text(
            f"❌ Cloudflare API: <code>{html.escape(str(e)[:500])}</code>",
            reply_markup=_back_kb(),
        )
        await state.clear()
        return
    except Exception as e:
        logger.exception("domain bind failed")
        await status.edit_text(
            f"❌ Ошибка: <code>{html.escape(str(e)[:500])}</code>",
            reply_markup=_back_kb(),
        )
        await state.clear()
        return

    user_domain_add(message.from_user.id, domain, account["id"])

    ns_text = "\n".join(f"• <code>{html.escape(ns)}</code>" for ns in ns_servers)
    await status.edit_text(
        f"✅ Домен <code>{html.escape(domain)}</code> привязан!\n\n"
        f"<b>NS-серверы Cloudflare</b> — пропишите их у регистратора домена:\n{ns_text}\n\n"
        "После смены NS дождитесь распространения (обычно 1–24 ч), затем "
        "сертификат выпустится автоматически через DNS-01.\n\n"
        "🔔 Как только SSL поднимется — пришлю сюда уведомление.",
        reply_markup=_back_kb(),
    )
    await state.clear()


def _bind_domain_sync(domain: str, cf_token: str) -> list[str]:
    """Синхронная проводка: CF zone + A + SSL + defaults + Caddy + reload."""
    ip = config.DOMAIN_SERVER_IP
    caddyfile = config.DOMAIN_CADDYFILE
    caddy_exe = config.DOMAIN_CADDY_EXE
    target = config.DOMAIN_TARGET

    zone_id = cf_create_or_get_zone(domain, cf_token)
    cf_add_a_record(zone_id, domain, ip, cf_token)
    cf_set_ssl_mode(zone_id, "strict", cf_token)
    cf_set_domain_defaults(zone_id, cf_token)
    ns_servers = cf_get_ns_servers(zone_id, cf_token)

    add_domain_to_caddy_with_token(domain, caddyfile, cf_token, target=target)
    try:
        reload_caddy(
            caddy_exe, caddyfile,
            admin_url=config.DOMAIN_CADDY_ADMIN_URL or None,
        )
    except CaddyReloadError:
        try:
            remove_domain_from_caddy(domain, caddyfile)
        except Exception:
            logger.exception("rollback remove_domain_from_caddy failed")
        raise

    return ns_servers
