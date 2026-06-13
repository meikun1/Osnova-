from __future__ import annotations

TEMPLATES: dict[str, str] = {
    "standard": "Стандартный шаблон (Для мини-апп)",
    "text": "Текстовый шаблон",
    "welcome": "Шаблон-приветствие",
}

DEFAULT_TEMPLATE = "standard"

def template_name(template_id: str | None) -> str:
    return TEMPLATES.get(template_id or DEFAULT_TEMPLATE, TEMPLATES[DEFAULT_TEMPLATE])
