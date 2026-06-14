"""Создание бота — теперь в два шага.

Подменю с тремя кнопками:
  🌐 Привязать домен      — запускает FSM domain_bind (handlers/domain.py)
  🤖 Добавить токен        — спрашивает токен, валидирует и сохраняет в pending_bots
  ✅ Проверить и создать   — если есть SSL-домен + pending токен → создаёт бота
"""
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from child.runtime import get_runtime
from database import (
    add_bot,
    get_bot,
    pending_bot_clear,
    pending_bot_get,
    pending_bot_set,
    token_exists,
    user_has_ssl_domain,
)
from handlers.ui import edit_anchor, remember_anchor

router = Router()

TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")


class CreateBot(StatesGroup):
    waiting_for_token = State()


def _menu_text(user_id: int) -> str:
    has_ssl = user_has_ssl_domain(user_id)
    pending = pending_bot_get(user_id)

    ssl_line = "🟢 домен с SSL привязан" if has_ssl else "🔴 домен не привязан / SSL не выпущен"
    if pending:
        tok_line = f"🟢 токен добавлен (@{pending['username']})"
    else:
        tok_line = "🔴 токен не добавлен"

    return (
        "⚙️ <b>Создание бота</b>\n\n"
        "Нужно выполнить два шага:\n"
        f"1. {ssl_line}\n"
        f"2. {tok_line}\n\n"
        "Когда оба пункта зелёные — жми «✅ Проверить и создать»."
    )


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Привязать домен", callback_data="domain_bind")],
            [InlineKeyboardButton(text="🤖 Добавить токен", callback_data="create_bot_token")],
            [InlineKeyboardButton(text="✅ Проверить и создать", callback_data="create_bot_check")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")],
        ]
    )


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="create_bot")]
        ]
    )


@router.callback_query(F.data == "create_bot")
async def open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        _menu_text(callback.from_user.id), reply_markup=_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "create_bot_token")
async def ask_token(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateBot.waiting_for_token)
    await remember_anchor(callback, state)
    await callback.message.edit_text(
        "🤖 <b>Добавление токена</b>\n\n"
        "1. Откройте @BotFather и отправьте <code>/newbot</code>\n"
        "2. Придумайте имя и username\n"
        "3. Скопируйте токен и пришлите его сюда 👇\n\n"
        "<i>Пример: 123456789:AaBbCcDdEe...</i>",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


@router.message(CreateBot.waiting_for_token, F.text, ~F.text.startswith("/"))
async def receive_token(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    token = message.text.strip()

    if not TOKEN_RE.match(token):
        await edit_anchor(
            message, data,
            "❌ Это не похоже на токен. Пришлите токен от @BotFather целиком.",
            _cancel_kb(),
        )
        return

    if token_exists(token):
        await edit_anchor(
            message, data, "⚠️ Этот бот уже добавлен.", _cancel_kb()
        )
        return

    child_bot = Bot(token=token)
    try:
        me = await child_bot.get_me()
    except TelegramUnauthorizedError:
        await edit_anchor(
            message, data,
            "❌ Токен недействителен (отклонён Telegram). Проверьте и пришлите снова.",
            _cancel_kb(),
        )
        return
    finally:
        await child_bot.session.close()

    pending_bot_set(message.from_user.id, token, me.username, me.id)
    await state.clear()

    await edit_anchor(
        message, data,
        f"✅ Токен принят: <b>@{me.username}</b>.\n\n"
        "Теперь привяжите домен (если ещё не сделано) и нажмите "
        "«✅ Проверить и создать».",
        _menu_kb(),
    )


@router.callback_query(F.data == "create_bot_check")
async def check_and_create(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    has_ssl = user_has_ssl_domain(user_id)
    pending = pending_bot_get(user_id)

    if not has_ssl and not pending:
        await callback.answer(
            "Не сделано: домен с SSL и токен.", show_alert=True
        )
        return
    if not has_ssl:
        await callback.answer(
            "Сначала дождитесь выпуска SSL по домену.", show_alert=True
        )
        return
    if not pending:
        await callback.answer(
            "Сначала добавьте токен бота.", show_alert=True
        )
        return

    # Финальная проверка токена через Telegram (вдруг отозвали за это время).
    child_bot = Bot(token=pending["token"])
    try:
        me = await child_bot.get_me()
    except TelegramUnauthorizedError:
        pending_bot_clear(user_id)
        await callback.message.edit_text(
            "❌ Токен оказался невалидным (отозван в @BotFather). "
            "Добавьте новый.",
            reply_markup=_menu_kb(),
        )
        await callback.answer()
        return
    finally:
        await child_bot.session.close()

    bot_id = add_bot(
        owner_id=user_id,
        token=pending["token"],
        username=f"@{me.username}",
        tg_id=me.id,
    )
    pending_bot_clear(user_id)
    await state.clear()

    await get_runtime().start_bot_db(get_bot(bot_id))

    await callback.message.edit_text(
        f"✅ Бот <b>@{me.username}</b> успешно добавлен и запущен!\n\n"
        "Теперь добавьте его в админы вашего закрытого канала, "
        "и настройте обработку заявок в разделе «Настройки добавления».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]
            ]
        ),
    )
    await callback.answer("Готово")
