"""Админ-панель. Доступна только тем, чей telegram id есть в config.ADMIN_IDS.

Сейчас умеет:
- показывать статистику пула CF-аккаунтов;
- добавлять новые api_token'ы прямо из чата (дубли пропускаются).
"""
from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from cf_pool_loader import append_token_to_json
from config import ADMIN_IDS
from database import cf_pool_add, cf_pool_stats

router = Router()


class CfPoolAdd(StatesGroup):
    waiting_tokens = State()


_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{30,}")


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _panel_text() -> str:
    s = cf_pool_stats()
    return (
        "🛠 <b>Админ-панель</b>\n\n"
        "<b>Пул Cloudflare-аккаунтов</b>\n"
        f"• Всего: <b>{s['total']}</b>\n"
        f"• Свободно: <b>{s['free']}</b>\n"
        f"• Занято: <b>{s['taken']}</b>"
    )


def _panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить CF-токены", callback_data="admin_cf_add")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_panel")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")],
        ]
    )


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
        ]
    )


@router.callback_query(F.data == "admin_panel")
async def open_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(_panel_text(), reply_markup=_panel_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_cf_add")
async def cf_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(CfPoolAdd.waiting_tokens)
    await callback.message.edit_text(
        "➕ <b>Добавить CF-токены в пул</b>\n\n"
        "Пришлите один или несколько API-токенов Cloudflare — по одному в строке "
        "или через пробелы/запятые. Дубли по уже существующим токенам "
        "пропускаются автоматически.\n\n"
        "<i>Формат: длинная строка, обычно начинается с <code>cfut_</code> "
        "или 40 символов hex.</i>",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


@router.message(CfPoolAdd.waiting_tokens, F.text)
async def cf_add_receive(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    tokens = _TOKEN_RE.findall(message.text or "")
    if not tokens:
        await message.answer(
            "❌ Не нашёл ни одного похожего на токен значения. Попробуйте ещё раз.",
            reply_markup=_cancel_kb(),
        )
        return

    added = 0
    rejected_non_ascii = 0
    dupes = 0
    file_synced = 0
    for token in tokens:
        if not token.isascii():
            rejected_non_ascii += 1
            continue
        if cf_pool_add(email=None, api_token=token, label=None):
            added += 1
            if append_token_to_json(token):
                file_synced += 1
        else:
            dupes += 1

    await state.clear()
    stats = cf_pool_stats()
    lines = [
        "✅ Готово.",
        f"• Добавлено новых: <b>{added}</b>",
        f"• Записано в cf_pool.json: <b>{file_synced}</b>",
        f"• Пропущено дублей: <b>{dupes}</b>",
    ]
    if rejected_non_ascii:
        lines.append(
            f"• ⚠️ Отклонено (не-ASCII символы): <b>{rejected_non_ascii}</b>\n"
            "  Это значит, что при копировании в токен попали кириллические "
            "буквы / неразрывные пробелы. Перевыпустите токен в Cloudflare "
            "и скопируйте кнопкой <b>Copy</b>."
        )
    lines.append(
        f"\nВ пуле всего: <b>{stats['total']}</b>, свободно: <b>{stats['free']}</b>."
    )
    await message.answer("\n".join(lines), reply_markup=_panel_kb())
