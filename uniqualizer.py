import random
import re

HOMOGLYPHS_LOWER = {
    'a': ['а', 'α', 'ɑ'],
    'b': ['Ь', 'Ƅ'],
    'c': ['с', 'ϲ', 'ⅽ', 'ᴄ'],
    'd': ['ⅾ', 'ԁ'],
    'e': ['е'],
    'f': ['ғ', 'ƒ'],
    'g': ['ɡ', 'ց'],
    'h': ['հ'],
    'i': ['і', 'ⅰ'],
    'j': ['ј', 'ϳ', 'ɉ'],
    'k': ['к', 'κ', 'ĸ'],
    'l': ['ӏ', 'Ɩ', 'ⅼ'],
    'm': ['м', 'ⅿ'],
    'n': ['ո', 'η', 'ᥒ'],
    'o': ['о', 'ο', 'օ'],
    'p': ['р', 'ρ', 'ⲣ'],
    'q': ['ԛ', 'զ'],
    'r': ['г', 'ɾ'],
    's': ['ѕ', 'ꜱ'],
    't': ['τ', 'ⲧ'],
    'u': ['υ', 'ս'],
    'v': ['ⅴ', 'ν', 'ѵ'],
    'w': ['ԝ', 'ѡ'],
    'x': ['х', 'ⅹ', 'ⲭ'],
    'y': ['у', 'γ'],
    'z': ['ʐ'],
}

HOMOGLYPHS_UPPER = {
    'A': ['А', 'Α', 'Ꭺ'],
    'B': ['В', 'Β', 'Ᏼ'],
    'C': ['С', 'Ⅽ', 'Ꮯ'],
    'D': ['Ⅾ', 'Ꭰ'],
    'E': ['Е', 'Ε', 'Ꭼ'],
    'F': ['Ϝ'],
    'G': ['Ԍ', 'Ꮐ'],
    'H': ['Н', 'Η', 'Ꮋ'],
    'I': ['І', 'Ι', 'Ⅰ'],
    'J': ['Ј', 'Ꭻ'],
    'K': ['К', 'Κ', 'Ꮶ'],
    'L': ['Ⅼ', 'Ꮮ'],
    'M': ['М', 'Μ', 'Ⅿ', 'Ꮇ'],
    'N': ['Ν', 'Ⲛ'],
    'O': ['О', 'Ο', 'ⵔ', 'Ⲟ'],
    'P': ['Р', 'Ρ', 'Ꮲ'],
    'Q': ['Ԛ'],
    'R': ['Ʀ'],
    'S': ['Ѕ', 'Ꮪ'],
    'T': ['Т', 'Τ', 'Ꭲ'],
    'U': ['Ս'],
    'V': ['Ⅴ', 'Ѵ', 'Ꮩ'],
    'W': ['Ԝ', 'Ꮃ'],
    'X': ['Х', 'Χ', 'Ⅹ'],
    'Y': ['У', 'Ү', 'Υ', 'Ꭹ'],
    'Z': ['Ζ', 'Ꮓ', 'ℤ'],
}

HOMOGLYPHS_HARD = {**HOMOGLYPHS_LOWER, **HOMOGLYPHS_UPPER}

HOMOGLYPHS_LIGHT = {
    'a': ['а'], 'c': ['с'], 'e': ['е'], 'i': ['і'],
    'j': ['ј'], 'k': ['к'], 'm': ['м'], 'o': ['о'],
    'p': ['р'], 's': ['ѕ'], 'x': ['х'], 'y': ['у'],
    'A': ['А'], 'B': ['В'], 'C': ['С'], 'E': ['Е'],
    'H': ['Н'], 'I': ['І'], 'J': ['Ј'], 'K': ['К'],
    'M': ['М'], 'O': ['О'], 'P': ['Р'], 'S': ['Ѕ'],
    'T': ['Т'], 'X': ['Х'], 'Y': ['У'],
}

_HTML_TAG_RE = re.compile(r'<[^>]+>')
_URL_RE = re.compile(r'https?://\S+')

def _build_protected_ranges(text: str) -> set:
    protected = set()
    for m in _HTML_TAG_RE.finditer(text):
        protected.update(range(m.start(), m.end()))
    for m in _URL_RE.finditer(text):
        protected.update(range(m.start(), m.end()))
    return protected

def uniqualize(text: str, homoglyph_ratio: float = 0.5, mode: str = "hard") -> str:
    if not text:
        return text

    glyphs = HOMOGLYPHS_LIGHT if mode == "light" else HOMOGLYPHS_HARD

    protected = _build_protected_ranges(text)
    chars = list(text)
    replaceable = [
        (i, ch) for i, ch in enumerate(chars)
        if ch in glyphs and i not in protected
    ]
    if not replaceable:
        return text

    count = max(1, int(len(replaceable) * homoglyph_ratio))
    targets = random.sample(replaceable, min(count, len(replaceable)))
    for idx, ch in targets:
        chars[idx] = random.choice(glyphs[ch])

    return ''.join(chars)

def generate_variants(text: str, count: int,
                      homoglyph_ratio: float = 0.5, mode: str = "hard") -> list:
    if count <= 0:
        return []
    return [uniqualize(text, homoglyph_ratio=homoglyph_ratio, mode=mode)
            for _ in range(count)]


# Поля контента шаблона, которые НЕ являются текстом и не уникализируются:
# оформление, флаги и сами настройки уникализации.
_NON_TEXT_KEYS = {
    "ui_color", "view", "bg", "blur", "app_name",
    "uniq_enabled", "uniq_ratio", "uniq_mode",
}


def _is_text_field(key: str, value) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if key in _NON_TEXT_KEYS:
        return False
    # эмодзи-поля (main_emoji, code_emoji, …) и одиночное "emoji" не трогаем
    if key == "emoji" or key.endswith("_emoji"):
        return False
    return True


def uniqualize_content(content: dict,
                       homoglyph_ratio: float = 0.5,
                       mode: str = "hard",
                       keys=None) -> dict:
    """Уникализирует ВЕСЬ текст шаблона за один вызов.

    Принимает словарь контента (плоский: start_msg, main_text, code_button…)
    и возвращает его копию, где у всех текстовых полей символы заменены на
    гомоглифы. URL и HTML-теги внутри текста сохраняются (см. uniqualize),
    эмодзи / цвета / view / флаги не трогаются.

    keys — если задан, обрабатываются только перечисленные поля.
    """
    out = dict(content)
    for key, value in content.items():
        if keys is not None and key not in keys:
            continue
        if not _is_text_field(key, value):
            continue
        out[key] = uniqualize(value, homoglyph_ratio=homoglyph_ratio, mode=mode)
    return out
