from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_bot, user_domains_list
from directlink_service import get_module
from handlers.cards import owns
from handlers.ui import edit_anchor, remember_anchor

router = Router()

class DLEdit(StatesGroup):
    waiting_desc = State()

async def _render(callback: CallbackQuery, bot: dict) -> None:
    tg_id = bot.get("tg_id")
    module = get_module()

    if not tg_id:
        await callback.message.edit_text(
            "⚠️ Бот ещё не инициализирован (нет telegram-id). "
            "Перезапустите бота и попробуйте снова.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"settings:{bot['id']}")]
                ]
            ),
        )
        return

    state = await module.get_or_init(tg_id)
    startapp_url = await module.build_url(tg_id)
    manual_url = module.config.manual_url
    enabled = state["enabled"]

    domains = user_domains_list(bot["owner_id"])
    domain = domains[-1]["domain"] if domains else "ваш-домен"
    miniapp_url = f"https://{domain}/app/{tg_id}"

    text = (
        "🔗 <b>Прямая ссылка</b>\n\n"
        "❓ Для включения необходимо открыть @BotFather → Bot Settings → "
        "<b>Configure Mini App</b> → <b>Edit Mini App URL</b> и вставить туда "
        "ссылку вашего мини-аппа:\n\n"
        f"<code>{miniapp_url}</code>\n\n"
        "<i>Формат: <code>https://&lt;ваш-домен&gt;/app/&lt;ID бота&gt;</code>. "
        "ID бота — это 10 цифр в начале токена бота (число до двоеточия).</i>\n\n"
        f'Подробный <a href="{manual_url}">мануал с картинками</a>. '
        "После сохранения ссылки в @BotFather прямая ссылка начнёт работать "
        "через 10–15 минут.\n\n"
        f"🔗 Прямая ссылка на мини-апп: {startapp_url}\n\n"
        "✳️ Вы можете отметить, что бот использует прямую ссылку, тогда он "
        "перестанет отвечать на /start\n\n"
        f"Статус: <b>{'🟢 включено' if enabled else '🔴 выключено'}</b>"
    )

    toggle = "🔴 Выключить" if enabled else "🟢 Включить"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle, callback_data=f"dl_toggle:{bot['id']}")],
            [
                InlineKeyboardButton(
                    text="✏️ Описание ссылки", callback_data=f"dl_desc:{bot['id']}"
                ),
                InlineKeyboardButton(
                    text="🖼 Аватар", callback_data=f"dl_avatar:{bot['id']}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"settings:{bot['id']}"
                )
            ],
        ]
    )
    try:
        await callback.message.edit_text(
            text, reply_markup=kb, disable_web_page_preview=True
        )
    except TelegramBadRequest:

        pass

@router.callback_query(F.data.startswith("dl:"))
async def open_direct_link(callback: CallbackQuery) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await _render(callback, bot)
    await callback.answer()

@router.callback_query(F.data.startswith("dl_toggle:"))
async def toggle_direct_link(callback: CallbackQuery) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    tg_id = bot.get("tg_id")
    if not tg_id:
        await callback.answer("Бот не инициализирован.", show_alert=True)
        return
    module = get_module()
    state = await module.get_or_init(tg_id)
    new_enabled = not state["enabled"]
    await module.storage.set_enabled(tg_id, new_enabled)

    from database import update_bot_field

    update_bot_field(bot["id"], "miniapp_enabled", 1 if new_enabled else 0)
    await _render(callback, bot)
    await callback.answer("🟢 Включено" if new_enabled else "🔴 Выключено")

@router.callback_query(F.data.startswith("dl_desc:"))
async def ask_desc(callback: CallbackQuery, state: FSMContext) -> None:
    bot = get_bot(int(callback.data.split(":")[1]))
    if not owns(callback.from_user.id, bot):
        await callback.answer("Бот не найден.", show_alert=True)
        return
    await state.set_state(DLEdit.waiting_desc)
    await state.update_data(bot_id=bot["id"])
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "✏️ <b>Описание прямой ссылки</b>\n\n"
        "Пришлите короткое описание (до 120 символов) — оно показывается в "
        "превью ссылки и в профиле бота.\n\n"
        "Чтобы очистить — отправьте «-».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"dl:{bot['id']}")]
            ]
        ),
    )
    await callback.answer()

@router.message(DLEdit.waiting_desc, F.text)
async def save_desc(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    bot = get_bot(data.get("bot_id"))
    if not bot:
        await message.answer("Бот не найден.")
        return
    text = message.text.strip()
    desc = "" if text == "-" else text[:120]
    child = Bot(token=bot["token"])
    try:
        await child.set_my_short_description(short_description=desc)
        ok, err = True, ""
    except Exception as e:
        ok, err = False, str(e)
    finally:
        await child.session.close()
    note = (
        "✅ Описание ссылки обновлено."
        if ok
        else f"⚠️ Не удалось обновить описание: {err}"
    )
    await edit_anchor(
        message,
        data,
        note,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Прямая ссылка", callback_data=f"dl:{bot['id']}")]
            ]
        ),
    )

@router.callback_query(F.data.startswith("dl_avatar:"))
async def avatar_info(callback: CallbackQuery) -> None:
    await callback.answer(
        "Аватар бота нельзя сменить через бота — только в @BotFather: "
        "/mybots → выберите бота → Edit Bot → Edit Botpic.",
        show_alert=True,
    )
