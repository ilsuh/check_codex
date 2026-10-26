"""Разметка, пояснения и ударения. Сетевых обращений здесь нет."""
from dataclasses import dataclass
from html.parser import HTMLParser
import re
import unicodedata

from .model import WordError

VOWELS = 'аеёиоуыэюя'
ACUTE = '\u0301'
GRAVE = '\u0300'


@dataclass(frozen=True)
class Markup:
    text: str
    italic: tuple[bool, ...]


class _Reader(HTMLParser):
    # Угловые грамматические указания не входят в этот список тегов.
    TAGS = {'i', 'em', 'b', 'strong', 'sup', 'sub', 'span', 'a', 'br', 'p', 'div'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.flags = []
        self.stack = []

    def append(self, value):
        self.parts.append(value.replace('\xa0', ' '))
        self.flags.extend([bool(self.stack)] * len(value))

    def handle_starttag(self, tag, attrs):
        if tag in ('i', 'em'):
            self.stack.append(tag)
        elif tag in ('br', 'p', 'div'):
            self.append(' ')
        elif tag not in self.TAGS:
            self.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in ('i', 'em'):
            if tag in self.stack:
                self.stack.remove(tag)
        elif tag in ('p', 'div'):
            self.append(' ')
        elif tag not in self.TAGS:
            self.append(f'</{tag}>')

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self.append(' ')
        elif tag not in self.TAGS:
            self.append(self.get_starttag_text())

    def handle_data(self, data):
        self.append(data)


def markup(value: str) -> Markup:
    reader = _Reader()
    reader.feed(value)
    reader.close()
    return Markup(''.join(reader.parts), tuple(reader.flags))


def plain(value: str) -> str:
    return markup(value).text.strip()


def word(value: str, *, headword=False, unstressed=False) -> dict:
    """Позиции относятся к буквам NFC, без комбинируемых знаков ударения."""
    value = unicodedata.normalize('NFC', value.strip())
    if headword:
        value = re.sub(r'^\d+(?:[-–]\d+)?\s*', '', value)
    letters = []
    primary, secondary = [], []
    for char in value:
        if char in (ACUTE, GRAVE):
            if not letters or letters[-1].lower() not in VOWELS:
                raise WordError('Знак ударения должен следовать за гласной.')
            positions = primary if char == ACUTE else secondary
            position = len(letters)
            if position in positions:
                raise WordError('Повторный знак ударения над одной буквой.')
            positions.append(position)
        else:
            letters.append(char)
    text = ''.join(letters)
    if not re.fullmatch(r'[А-Яа-яЁё]+(?:[- ][А-Яа-яЁё]+)*', text):
        raise WordError('Ожидается русское слово или составное заглавное слово.')
    if set(primary) & set(secondary):
        raise WordError('Основное и побочное ударение не могут совпадать.')
    if unstressed:
        if primary or secondary or any(c.lower() == 'ё' for c in text):
            raise WordError('Помета безударности противоречит указанному ударению.')
        return {'text': text, 'accent_variants': [
            {'primary': [], 'secondary': [], 'basis': 'unstressed'}]}
    yos = [i + 1 for i, c in enumerate(text) if c.lower() == 'ё' and i + 1 not in secondary]
    accented = sorted(set(primary + yos))
    if accented:
        # Для дефисного слова сохраняем одновременные ударения частей.
        # Пробелы тоже отделяют самостоятельные части составного заглавия.
        groups = [accented] if '-' in text or ' ' in text else [[p] for p in accented]
        variants = [{'primary': ps, 'secondary': secondary.copy(),
                     'basis': 'explicit' if any(p in primary for p in ps) else 'yo'} for ps in groups]
    else:
        vowels = [i + 1 for i, c in enumerate(text) if c.lower() in VOWELS]
        if len(vowels) == 1 and vowels[0] not in secondary:
            variants = [{'primary': vowels, 'secondary': secondary, 'basis': 'monosyllabic'}]
        else:
            variants = [{'primary': [], 'secondary': secondary, 'basis': 'missing'}]
    return {'text': text, 'accent_variants': variants}


_GRAMMATICAL = re.compile(
    r'^(?:[ИРДВТП]\.|(?:ед|мн|кф|сравн|прич|деепр|спряж|склон|нет|безл|формы?|'
    r'повел|наст|буд|прош|одуш|неодуш|род|удар|только|кроме)\b|'
    r'употр\.\s*(?:только|преимущ)|не\s+(?:имеет|употр))', re.I)
_REGISTER = {'простореч.', 'разг.', 'устар.', 'книжн.', 'спец.', 'обл.', 'поэт.'}


def _annotation_group(content: str, flags: tuple[bool, ...]):
    """Распознаём пояснения по структуре курсива, сохраняя неизвестные скобки."""
    if content.strip() == 'без удар.':
        return [{'kind': 'usage', 'text': 'без удар.'}]
    offset = len(content) - len(content.lstrip())
    if offset == len(content) or not flags[offset]:
        return None
    end = offset
    while end < len(content) and flags[end]:
        end += 1
    first = content[offset:end].strip()
    if not first or _GRAMMATICAL.match(first):
        return None
    tail = content[end:].strip()
    if first.startswith('косв. формы употребляются'):
        return [{'kind': 'usage', 'text': content.strip()}]
    if first == 'без удар.' and not tail:
        return [{'kind': 'usage', 'text': first}]
    if re.match(r'^(?:нормально |часто )?без удар', first):
        # Более сложные условия безударности требуют собственного правила;
        # они не превращаются в толкование и не исчезают из грамматики.
        return None
    kind = 'register' if first in _REGISTER else 'meaning'
    notes = [{'kind': kind, 'text': first}]
    # Указание «без указания предмета» относится к значению местоимения.
    while tail.startswith('['):
        close = tail.find(']')
        if close < 0:
            return None
        notes.append({'kind': 'usage', 'text': tail[1:close].strip()})
        tail = tail[close + 1:].strip()
    if tail:
        if not tail.startswith(':'):
            return None
        remaining = tail[1:].strip()
        if remaining:
            notes.append({'kind': 'meaning' if kind == 'register' else 'example', 'text': remaining})
    return notes


def description(value: str) -> tuple[str, list[dict]]:
    rendered = markup(value)
    text, flags = rendered.text, rendered.italic
    # Фразеологический блок начинается на верхнем уровне статьи.
    depth = 0
    phrase = None
    limit = len(text)
    for i, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif not depth and char in '✧◇⟡':
            phrase = text[i + 1:].strip(' ;')
            limit = i
            break
    notes, pieces = [], []
    start, opening, depth = 0, 0, 0
    for i in range(limit):
        char = text[i]
        if char == '(':
            if not depth:
                opening = i
            depth += 1
        elif char == ')' and depth:
            depth -= 1
            if not depth:
                annotation = _annotation_group(text[opening + 1:i], flags[opening + 1:i])
                if annotation and any(c in text[:opening] for c in '△Δ') and any(n['kind'] == 'register' for n in annotation):
                    # После знака исключений помета относится к конкретной
                    # выписанной форме и должна остаться рядом с ней.
                    annotation = None
                if annotation is not None:
                    pieces.append(text[start:opening])
                    pieces.append(' ')
                    notes.extend(annotation)
                    start = i + 1
    pieces.append(text[start:limit])
    if phrase:
        notes.append({'kind': 'phraseology', 'text': phrase})
    grammar = ''.join(pieces).strip(' ;')
    grammar = grammar.translate(str.maketrans({'’': "'", '′': "'", '″': "''"}))
    return grammar, notes
