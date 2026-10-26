"""Разбор JSON-описаний Грамматического словаря, склонение и спряжение."""
import re
from .model import InputError, WordError, diagnose, result
from .parser import parse_article
from .references import resolve
from .text import plain, word

__all__ = ['analyze', 'generate', 'generate_analyzed', 'InputError']
__version__ = '0.4.0'


def analyze(payload: dict | list[dict]) -> list[dict]:
    """Разбирает одну статью или группу; состояние между вызовами не хранится.

    Ошибка структуры документа вызывает InputError. Ошибки конкретных объектов
    остаются в результатах, сохраняя порядок и исходные данные.
    """
    if isinstance(payload, dict):
        if 'entries' in payload and 'lemma' not in payload:
            raise InputError('Ожидается один объект с lemma или массив таких объектов.')
        sources = [payload]
    elif isinstance(payload, list):
        sources = payload
    else:
        raise InputError('Ожидается один объект с lemma или массив таких объектов.')
    if any(not isinstance(article, dict) for article in sources):
        raise InputError('Каждый элемент массива должен быть объектом.')
    items = []
    previous = previous_index = None
    for i, source in enumerate(sources):
        item = result(source, i)
        items.append(item)
        explicit = isinstance(source.get('lemma'), str) and bool(source['lemma'].strip())
        if explicit:
            previous, previous_index = source['lemma'], i
        invalid = next((key for key in ('lemma', 'symbol', 'grammar')
                        if not isinstance(source.get(key), str)), None)
        if invalid:
            diagnose(item, 'invalid', 'INVALID_INPUT', f'Поле {invalid} должно быть строкой.')
            continue
        if not plain(source['symbol']).strip(' ,;'):
            diagnose(item, 'invalid', 'INVALID_INPUT', 'Поле symbol не должно быть пустым.')
            continue
        if previous is None:
            diagnose(item, 'invalid', 'INVALID_INPUT', 'Пустая lemma: в группе нет предыдущего слова.')
            continue
        item['effective_lemma'] = previous
        item['inherited_from'] = None if explicit else previous_index
        try:
            unstressed = bool(re.search(r'\(\s*без удар\.\s*\)', plain(source['grammar'])))
            item['headword'] = word(plain(previous), headword=True, unstressed=unstressed)
        except WordError as exc:
            diagnose(item, 'invalid', 'INVALID_INPUT', str(exc))
            continue
        parse_article(item)
    resolve(items)
    return items


from .generation import generate, generate_analyzed
