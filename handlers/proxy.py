from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    add_proxy,
    delete_proxy,
    get_bot,
    get_owner_proxies,
    get_proxy,
    set_bot_proxy,
)
from handlers.cards import owns
from handlers.ui import edit_anchor, remember_anchor

router = Router()

class Proxy(StatesGroup):
    waiting_for_proxy = State()

def _normalize(line: str) -> str | None:
    line = line.strip()
    if not line:
        return None
    if "://" in line:
        return line
    parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    return None

def _mask(url: str) -> str:
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url

def _label(p: dict) -> str:
    return p.get("label") or _mask(p["url"])

def _kb(bot: dict, proxies: list[dict]) -> InlineKeyboardMarkup:
    bid = bot["id"]
    current = bot.get("proxy_id")
    b = InlineKeyboardBuilder()

    mark = "✅ " if not current else ""
    b.row(
        InlineKeyboardButton(
            text=f"{mark}❌ Без прокси", callback_data=f"proxy_set:{bid}:0"
        )
    )
    for p in proxies:
        sel = "✅ " if p["id"] == current else ""
        b.row(
            InlineKeyboardButton(
                text=f"{sel}{_label(p)}", callback_data=f"proxy_set:{bid}:{p['id']}"
            )
        )
        b.row(
            InlineKeyboardButton(
                text="🗑 Удалить из пула", callback_data=f"proxy_del:{bid}:{p['id']}"
            )
        )
    b.row(
        InlineKeyboardButton(
            text="➕ Добавить прокси", callback_data=f"proxy_add:{bid}"
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"settings:{bid}"))
    return b.as_markup()

def _text(bot: dict, proxies: list[dict]) -> str:
    cur = bot.get("proxy_id")
    if cur:
        p = next((x for x in proxies if x["id"] == cur), None)
        now = _label(p) if p else "—"
    else:
        now = "без прокси"
    return (
        "🌐 <b>Выбор прокси</b>\n\n"
        "Пул прокси для поднятия ботов (общий для всех ваших ботов).\n"
        f"Сейчас у бота: <b>{now}</b>\n\n"
        "Выберите прокси из пула или добавьте новый."
    )

async def _show(callback: CallbackQuery, bot: dict) -> None:
    proxies = get_owner_proxies(callback.from_user.id)
    await callback.message.edit_text(
        _text(bot, proxies), reply_markup=_kb(bot, proxies)
    )

@router.callback_query(F.data.startswith("proxy:"))
async def open_proxy(callback: CallbackQuery) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await _show(callback, bot)
    await callback.answer()

@router.callback_query(F.data.startswith("proxy_set:"))
async def set_proxy(callback: CallbackQuery) -> None:
    _, bid_s, pid_s = callback.data.split(":")
    bid, pid = int(bid_s), int(pid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    set_bot_proxy(bid, pid or None)

    from child.runtime import get_runtime

    await get_runtime().restart_bot(bid)
    await _show(callback, get_bot(bid))
    await callback.answer("Прокси применён, бот перезапущен ✅")

@router.callback_query(F.data.startswith("proxy_del:"))
async def del_proxy(callback: CallbackQuery) -> None:
    _, bid_s, pid_s = callback.data.split(":")
    bid, pid = int(bid_s), int(pid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    proxy = get_proxy(pid)
    if proxy is None or proxy["owner_id"] != callback.from_user.id:
        await callback.answer("Прокси не найден.", show_alert=True)
        return
    delete_proxy(pid)
    await _show(callback, get_bot(bid))
    await callback.answer("Удалено 🗑")

@router.callback_query(F.data.startswith("proxy_add:"))
async def ask_proxy(callback: CallbackQuery, state: FSMContext) -> None:
    bid = int(callback.data.split(":")[1])
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await state.set_state(Proxy.waiting_for_proxy)
    await state.update_data(bid=bid)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "➕ Пришлите прокси (можно несколько, по одному в строке):\n\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>http://user:pass@host:port</code>\n"
        "<code>host:port:user:pass</code>\n"
        "<code>host:port</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"proxy:{bid}")]
            ]
        ),
    )
    await callback.answer()

@router.message(Proxy.waiting_for_proxy, F.text)
async def save_proxy(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    bid = data.get("bid")
    added, bad = 0, 0
    for line in message.text.splitlines():
        url = _normalize(line)
        if url:
            add_proxy(message.from_user.id, url)
            added += 1
        elif line.strip():
            bad += 1
    bot = get_bot(bid)
    proxies = get_owner_proxies(message.from_user.id)
    note = f"✅ Добавлено прокси: {added}"
    if bad:
        note += f"\n⚠️ Не распознано строк: {bad}"
    if bot:
        note += "\n\n" + _text(bot, proxies)
    await edit_anchor(message, data, note, _kb(bot, proxies) if bot else None)
