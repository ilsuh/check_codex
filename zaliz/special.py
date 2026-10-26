"""Дополнительные словарные указания и выписанные исключения.

Текст разбирается по грамматическим меткам. Совпадение с заранее известной
леммой не используется; непонятый остаток возвращается основному парсеру.
"""
from copy import deepcopy
import re

from .model import WordError, restriction
from .text import word

CASE_NAMES = dict(zip('ИРДВТП', ('nominative', 'genitive', 'dative', 'accusative',
                               'instrumental', 'prepositional')))
MARKS = '\u0301\u0300\u0341'


def additional(r, grammar):
    """П2 и Р2 не подменяют обычные предложный и родительный падежи."""
    def consume(m):
        if r['part_of_speech'] != 'noun': return m[0]
        if m['case'] == 'Р' and m['prep']: return m[0]
        spec = {'case': 'partitive' if m['case'] == 'Р' else 'locative',
                'optional': bool(m['open']), 'preposition': m['prep']}
        if bool(m['open']) != bool(m['close']): return m[0]
        r['inflection'].setdefault('extra_cases', []).append(spec)
        return ''
    return re.sub(r'(?P<open>\[)?(?P<case>[РП])2(?:\s*\((?P<prep>во?|на)\))?(?P<close>\])?', consume, grammar)


def restrictions(r, grammar):
    # Набор селекторов отражает простые пометы txt2adb; сложные условия
    # употребления не превращаются в безусловное отсутствие формы.
    selectors = {
        'Р. мн.': {'case': 'genitive', 'number': 'plural'},
        'мн.': {'number': 'plural'}, 'повел.': {'form': 'imperative'},
        'деепр.': {'form': 'gerund', 'tense': 'present'},
        'кф': {'form': 'short'}, 'сравн.': {'form': 'comparative'},
        'прош.': {'form': 'finite', 'tense': 'past'},
        'наст. 1 ед.': {'form': 'finite', 'tense': 'present', 'person': 1, 'number': 'singular'},
        'буд. 1 ед.': {'form': 'finite', 'tense': 'future', 'person': 1, 'number': 'singular'},
        'буд.': {'form': 'finite', 'tense': 'future'},
        'прич. страд. наст.': {'form': 'participle', 'voice': 'passive', 'tense': 'present'},
    }
    pattern = '|'.join(re.escape(label) for label in sorted(selectors, key=len, reverse=True))
    def consume(m):
        selector = selectors[m[1]]
        pos = r['part_of_speech']
        if 'case' in selector and pos != 'noun' or selector.get('form') in ('finite', 'imperative', 'gerund', 'participle') and pos != 'verb':
            return m[0]
        if selector.get('form') in ('short', 'comparative') and pos != 'adjective': return m[0]
        r['restrictions'].append(restriction(deepcopy(selector),
            {'нет': 'absent', 'затрудн.': 'difficult', 'предполож.': 'tentative'}[m[2]], m[0]))
        return ''
    return re.sub(r'(' + pattern + r')\s+(нет|затрудн\.|предполож\.)', consume, grammar)


def _values(text):
    """Варианты и типографские пометы сохраняются раздельно."""
    result = []
    for raw in re.split(r'//', text.strip(' ,;')):
        raw = raw.strip()
        state, note = 'normal', ''
        for marker, status in (('(затрудн.)', 'difficult'), ('(предполож.)', 'tentative'), ('(устар.)', 'normal')):
            if raw.endswith(marker):
                raw, state, note = raw[:-len(marker)].strip(), status, marker[1:-1]
                break
        if not raw: raise WordError('Пустой вариант нерегулярной формы.')
        result.append((raw, state, note))
    return result


def _expanded(raw, stem, previous):
    if '|' in raw:
        if raw.count('|') != 1: raise WordError('В форме допускается один разделитель основы |.')
        stem, ending = raw.split('|')
        if not stem: raise WordError('Перед | нужна основа.')
        return stem + ending, stem
    if raw.startswith('-'):
        if stem is None:
            if previous is None: raise WordError('Для сокращённой формы не задана основа.')
            # При отсутствии | сокращение заменяет только окончание:
            # дети, -ей неоднозначно; такие случаи требуют явного разделителя.
            raise WordError('Для сокращённых окончаний укажите основу через |.')
        suffix = raw[1:]
        # Явное ударение в окончании отменяет основное ударение основы.
        prefix = re.sub('[\u0301\u0341]', '', stem) if any(c in suffix for c in '\u0301\u0341') or 'ё' in suffix else stem
        return prefix + suffix, stem
    return raw, stem


def exceptions(r, text):
    """Выписанные формы регулярной статьи заменяют только свои позиции.

    Поддерживаются падежи с числом, полный перечень мн. числа, личные формы,
    императив, прошедшее, причастия и деепричастия. Границы разделов явные.
    """
    from .parser import Unsupported
    noun_label = r'[ИРДВТП]\.(?:\s*(?:ед|мн)\.)?|мн\.'
    verb_label = r'наст\.|буд\.|прош\.|повел\.|прич\.\s*(?:страд\.|действ\.)(?:\s*(?:наст|прош)\.)?|деепр\.\s*(?:наст|прош)\.'
    label = noun_label if r['part_of_speech'] == 'noun' else verb_label if r['part_of_speech'] == 'verb' else r'кф|сравн\.'
    pattern = re.compile(r'^(' + label + r')\s*(.*)$', re.S)
    stem = previous = None
    for section in text.strip(' :;,').split(';'):
        if not section.strip(): continue
        m = pattern.match(section.strip())
        if not m: raise Unsupported(section, 'Не распознана метка нерегулярной формы.')
        name, values = m.groups()
        if not values.lstrip().startswith('-'): stem = None
        entries = [v.strip() for v in values.split(',')]
        if name == 'мн.':
            if len(entries) not in (1, 5, 6): raise Unsupported(section, 'Перечень мн. числа требует 1, 5 или 6 позиций.')
            cases = ('nominative', 'genitive', 'dative', 'instrumental', 'prepositional') if len(entries) == 5 else tuple(CASE_NAMES.values())
            features = [{'case': c, 'number': 'plural'} for c in cases][:len(entries)]
        elif r['part_of_speech'] == 'noun':
            if len(entries) != 1: raise Unsupported(section, 'Разделяйте падежные формы точкой с запятой.')
            features = [{'case': CASE_NAMES[name[0]], 'number': 'plural' if 'мн.' in name else 'singular'}]
        elif name in ('наст.', 'буд.'):
            if len(entries) not in (1, 2, 6): raise Unsupported(section, 'Личный ряд требует 1, 2 или 6 позиций.')
            positions = [(1, 'singular'), (3, 'singular')] if len(entries) == 2 else [(p, n) for n in ('singular', 'plural') for p in (1, 2, 3)]
            features = [{'form': 'finite', 'tense': 'present' if name == 'наст.' else 'future', 'person': p, 'number': n} for p, n in positions][:len(entries)]
        elif name == 'прош.':
            if len(entries) not in (1, 2, 4): raise Unsupported(section, 'Прошедшее требует 1, 2 или 4 позиций.')
            features = [{'form': 'finite', 'tense': 'past', 'number': 'singular', 'gender': g} for g in ('masculine', 'feminine', 'neuter')]
            features.append({'form': 'finite', 'tense': 'past', 'number': 'plural'})
            features = features[:len(entries)]
        elif name == 'повел.':
            if len(entries) not in (1, 2): raise Unsupported(section)
            features = [{'form': 'imperative', 'person': 2, 'number': n} for n in ('singular', 'plural')][:len(entries)]
        elif name.startswith('прич.'):
            if len(entries) != 1: raise Unsupported(section)
            features = [{'form': 'participle', 'voice': 'passive' if 'страд.' in name else 'active',
                         'tense': 'present' if 'наст.' in name else 'past'}]
        elif name.startswith('деепр.'):
            if len(entries) != 1: raise Unsupported(section)
            features = [{'form': 'gerund', 'tense': 'present' if 'наст.' in name else 'past'}]
        elif name == 'сравн.':
            if len(entries) != 1: raise Unsupported(section)
            features = [{'form': 'comparative'}]
        else:
            if len(entries) != 4: raise Unsupported(section, 'Краткий ряд требует четыре позиции.')
            features = [{'form': 'short', 'number': 'singular', 'gender': g} for g in ('masculine', 'feminine', 'neuter')]
            features.append({'form': 'short', 'number': 'plural'})
        for feature, entry in zip(features, entries):
            for raw, status, note in _values(entry):
                expanded, stem = _expanded(raw, stem, previous)
                normalized = word(expanded)
                if any(a['basis'] == 'missing' for a in normalized['accent_variants']):
                    raise WordError('Укажите ударение в нерегулярной форме.')
                r['explicit_forms'].append({'features': deepcopy(feature), 'word': normalized, 'status': status, 'note': note})
                if stem is None:
                    if feature.get('form') == 'finite' and feature.get('tense') in ('present', 'future') and feature.get('person') == 1:
                        stem = re.sub(r'[уюм][\u0301\u0341]?(?:с[яь])?$', '', expanded)
                    elif feature.get('form') == 'finite' and feature.get('tense') == 'past':
                        stem = re.sub('с[яь]$', '', expanded)
                    elif feature.get('case') == 'nominative' and feature.get('number') == 'plural':
                        stem = re.sub(r'[аяыийь](?:[\u0301\u0341])?$', '', expanded)
                previous = expanded
