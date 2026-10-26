"""Разбор словарных обозначений в модель версии 1, без генерации форм."""
from copy import deepcopy
import re

from .model import diagnose, reading, relation, restriction, WordError
from .text import description, plain, word
from . import special

GENDERS = {'м': 'masculine', 'ж': 'feminine', 'с': 'neuter'}
CASES = dict(zip('ИРДВТП', ('nominative', 'genitive', 'dative', 'accusative',
                           'instrumental', 'prepositional')))
CIRCLES = '①②③④⑤⑥⑦⑧⑨'
LATIN = str.maketrans({'а': 'a', 'с': 'c', 'е': 'e'})
INDEX = re.compile(r'^(\d{1,2})(\*\*|\*|°|ᵒ|⁰)?\s*([a-fасе](?:\x27{1,2})?)?(?:/([abcас](?:\x27{1,2})?))?')
PARTNER = re.compile(r'◑(I{1,3}|1[0-6]|[1-9])(?:\(([^()]*)\))?')


class Unsupported(ValueError):
    def __init__(self, fragment, message=None):
        self.fragment = fragment.strip()
        self.message = message or f'Неизвестное обозначение: {self.fragment}.'
        super().__init__(self.message)


def _remainder(value):
    return value.strip(' \t\r\n,;')


def _verb(headword, symbol, grammar):
    reflexive = headword['text'].lower().endswith(('ся', 'сь'))
    marker = bool(re.search(r'\bнп\b', grammar))
    return {'aspect': {'св': 'perfective', 'нсв': 'imperfective', 'св-нсв': 'biaspectual'}[symbol],
            'transitivity': 'intransitive' if marker or reflexive else 'transitive',
            'transitivity_basis': 'explicit_marker' if marker else 'reflexive' if reflexive else 'dictionary_default',
            'reflexive': reflexive, 'partner': None}


def _restrictions(r, rest):
    pos = r['part_of_speech']
    if pos not in ('adjective', 'verb'):
        return rest
    selector = {'form': 'short'} if pos == 'adjective' else {'form': 'participle', 'tense': 'past', 'voice': 'passive'}
    # Порядок ограничений следует порядку исходных знаков. Более конкретное
    # отсутствие формы сохраняется отдельно от общей затруднительности.
    def consume(match):
        marker = match[0]
        if marker in '✕×':
            r['restrictions'].append(restriction(selector.copy(), 'difficult', marker))
        elif marker in '⌧☒':
            if pos == 'adjective':
                r['restrictions'].append(restriction(selector.copy(), 'difficult', marker))
                r['restrictions'].append(restriction({'form': 'short', 'gender': 'masculine'}, 'absent', marker))
            else:
                r['restrictions'].append(restriction(selector.copy(), 'absent', marker))
        elif pos == 'adjective':
            r['restrictions'].append(restriction({'form': 'comparative'}, 'absent', marker))
        else:
            return marker
        return ''
    return re.sub('[✕×⌧☒~∼]', consume, rest)


def _parse_regular(r, grammar):
    f = r['inflection']
    wrapped = re.match(r'^<\s*(мс|п|[мжс]о?)\s+([^<>]+)>(.*)$', grammar, flags=re.S)
    if wrapped:
        pattern, inner, tail = wrapped.groups()
        if pattern in ('п', 'мс'):
            f['family'] = 'adjectival' if pattern == 'п' else 'pronominal'
        else:
            f['pattern_gender'] = GENDERS[pattern[0]]
            f['pattern_animacy'] = 'animate' if pattern.endswith('о') else 'inanimate'
        grammar = inner.strip() + ' ' + tail
    match = INDEX.match(grammar)
    if not match or not match[3] and match[1] != '0':
        raise Unsupported(grammar, f'Не удалось разобрать индекс: {grammar!r}.')
    index = int(match[1])
    maximum = 16 if f['family'] == 'verbal' else 8
    if index > maximum or f['family'] == 'verbal' and index == 0:
        raise WordError(f'Недопустимый номер типа словоизменения: {index}.')
    f['index'] = index
    f['fleeting_vowel'] = match[2] == '*'
    f['special_alternation'] = match[2] in ('**', '°', 'ᵒ', '⁰')
    f['stress']['full'] = match[3].translate(LATIN) if match[3] else None
    if match[4]:
        if r['part_of_speech'] not in ('adjective', 'verb') and f['family'] not in ('adjectival', 'pronominal'):
            raise Unsupported('/' + match[4], 'Вторая схема ударения неприменима к этому разбору.')
        target = 'past' if r['part_of_speech'] == 'verb' else 'short'
        f['stress'][target] = match[4].translate(LATIN)
    rest = grammar[match.end():]
    alternatives = []
    while r['part_of_speech'] == 'verb':
        alternative = re.match(r'^\s*//\s*(\d{1,2}(?:\*\*|\*|°)?[a-f](?:\x27{1,2})?(?:/[abc](?:\x27{1,2})?)?)', rest)
        if not alternative: break
        alternate_reading = deepcopy(r)
        _parse_regular(alternate_reading, alternative[1])
        alternatives.append(alternate_reading['inflection'])
        rest = rest[alternative.end():]
    if alternatives: f['alternatives'] = alternatives
    if r['verb']:
        partners = list(PARTNER.finditer(rest))
        if len(partners) > 1:
            raise Unsupported(rest, 'Несколько видовых указаний требуют отдельного разбора вариантов.')
        if partners:
            p = partners[0]
            aspect = r['verb']['aspect']
            if aspect == 'biaspectual':
                raise Unsupported(p[0], 'Не указано направление видовой связи двувидового глагола.')
            r['verb']['partner'] = {
                'direction': 'to_imperfective' if aspect == 'perfective' else 'to_perfective',
                'type': p[1], 'replacement': p[2], 'raw': p[0],
            }
            rest = rest[:p.start()] + rest[p.end():]
        elif '◑' in rest:
            explicit_partner = re.search(r'◑\s*([А-Яа-яЁё\u0301\u0300\u0341]+)', rest)
            if explicit_partner and r['verb']['aspect'] != 'biaspectual':
                p = explicit_partner
                target = word(p[1])
                if any(a['basis'] == 'missing' for a in target['accent_variants']):
                    raise WordError('Укажите ударение в видовом партнёре.')
                r['verb']['partner'] = {'direction': 'to_imperfective' if r['verb']['aspect'] == 'perfective' else 'to_perfective',
                    'type': 'explicit', 'replacement': p[1], 'raw': p[0]}
                rest = rest[:p.start()] + rest[p.end():]
    def deviation(m):
        optional = m[1] is not None
        for ch in m[1] or m[2]:
            r['deviations'].append({'number': CIRCLES.index(ch) + 1, 'optional': optional})
        return ''
    rest = re.sub(r'\[([' + CIRCLES + r']+)\]|([' + CIRCLES + '])', deviation, rest)
    alternations = list(re.finditer(r'\(\s*[-–]([а-яё]+)[-–]\s*\)', rest))
    if len(alternations) > 1:
        raise Unsupported(rest, 'Несколько согласных чередований требуют отдельного разбора.')
    if alternations:
        alt = alternations[0]
        f['consonant_alternation'] = alt[1]
        rest = rest[:alt.start()] + rest[alt.end():]
    # Дополнительное поле появляется только при явной словарной помете.
    # Прежние эталоны без неё остаются побайтово совместимыми по модели.
    yo = re.compile(r'(^|[\s,])ё(?=$|[\s,])')
    if yo.search(rest):
        f['yo_alternation'] = True
        rest = yo.sub(r'\1', rest)
    rest = special.additional(r, rest)
    rest = special.restrictions(r, rest)
    rest = _restrictions(r, rest)
    def paragraph(m):
        r['inflection'].setdefault('paragraphs', []).append(int(m[1]))
        return ''
    rest = re.sub(r'§\s*(\d+)', paragraph, rest)
    if _remainder(rest):
        raise Unsupported(_remainder(rest))
    if r['number_scope'] == 'plural_only' and not f['pattern_gender']:
        raise Unsupported(grammar, 'Для мн. нужен явно заданный образец рода, например <м 5*b>.')


def _explicit_form(features, value):
    normalized = word(value)
    if any(a['basis'] == 'missing' for a in normalized['accent_variants']):
        raise WordError('В выписанной форме необходимо указать ударение.')
    return {'features': features, 'word': normalized, 'status': 'normal', 'note': ''}


def _parse_explicit(r, grammar, headword):
    """Разворачиваем выписанные формы и связи равенства, не вычисляя парадигму."""
    r['inflection']['kind'] = 'explicit'
    r['inflection']['family'] = 'explicit'
    r['explicit_forms'] = [{'features': {'case': 'nominative'}, 'word': deepcopy(headword),
                            'status': 'normal', 'note': ''}]
    relations = []
    pattern = r'([ИРДВТП])\.\s*(неод\.|одуш\.)?\s*=\s*([ИРДВТП])\.(?:\s*или\s*([ИРДВТП])\.)?'
    def equality(m):
        target = {'case': CASES[m[1]]}
        sources = [{'case': CASES[c]} for c in (m[3], m[4]) if c]
        if m[2]:
            target['animacy'] = 'animate' if m[2] == 'одуш.' else 'inanimate'
            relations.append(relation(target, *sources))
        elif r['part_of_speech'] == 'numeral' and m[1] == 'В':
            for animacy in ('inanimate', 'animate'):
                relations.append(relation({**target, 'animacy': animacy}, *deepcopy(sources)))
        else:
            relations.append(relation(target, *sources))
        return ''
    grammar = re.sub(pattern, equality, grammar)
    closed = 'других форм нет' in grammar
    grammar = grammar.replace('других форм нет', '')
    labels = r'((?:[ИРДВТП]\.\s*,?\s*)+)'
    pieces = re.split(labels, _remainder(grammar))
    if _remainder(pieces[0]):
        raise Unsupported(_remainder(pieces[0]), 'Не удалось разобрать перечень выписанных форм.')
    stem = None
    for label, values in zip(pieces[1::2], pieces[2::2]):
        cases = [CASES[c] for c in re.findall('[ИРДВТП]', label)]
        variants = re.split(r'//|,', _remainder(values))
        if not variants or any(not v.strip() for v in variants):
            raise Unsupported(values, 'После грамматической метки отсутствует словоформа.')
        for value in variants:
            value = value.strip()
            if '|' in value:
                if value.count('|') != 1:
                    raise Unsupported(value)
                stem, ending = value.split('|')
                if not stem:
                    raise Unsupported(value)
                value = stem + ending
            elif value.startswith('-'):
                if stem is None:
                    raise Unsupported(value, 'Сокращённое окончание не имеет заданной основы.')
                value = stem + value[1:]
            for case in cases:
                form = _explicit_form({'case': case}, value)
                if case == 'nominative':
                    r['explicit_forms'] = [f for f in r['explicit_forms'] if f['features']['case'] != case]
                r['explicit_forms'].append(form)
    # Порядок падежей в модели не зависит от сокращения «Р., П.» в статье.
    case_order = {case: i for i, case in enumerate(CASES.values())}
    r['explicit_forms'].sort(key=lambda f: case_order[f['features']['case']])
    r['relations'] = relations
    available = {f['features']['case'] for f in r['explicit_forms']}
    available.update(rel['target']['case'] for rel in relations)
    if closed:
        for case in CASES.values():
            if case not in available:
                r['restrictions'].append(restriction({'case': case}, 'absent', 'других форм нет'))
    elif not set(CASES.values()).issubset(available):
        raise Unsupported(grammar, 'Неполный перечень падежных форм.')


def parse_description(item: dict) -> None:
    """Заполняет один результат; контекст лемм и связей находится вне парсера."""
    source, headword = item['source'], item['headword']
    symbol = plain(source['symbol']).strip(' ,;')
    grammar, notes = description(source['grammar'])
    item['annotations'] = notes
    noun = re.fullmatch(r'([мжс])(о)?', symbol)
    plural = re.fullmatch(r'мн\.(?:\s*(неод\.|неодуш\.|одуш\.))?', symbol)
    if noun:
        r = reading('noun', GENDERS[noun[1]], 'animate' if noun[2] else 'inanimate')
    elif plural:
        r = reading('noun', None, 'animate' if plural[1] == 'одуш.' else 'unspecified')
        r['number_scope'] = 'plural_only'
    elif symbol == 'ф.':
        r = reading('surname', None, 'animate')
    elif symbol in ('п', 'мс-п', 'числ.-п'):
        r = reading('adjective')
        if symbol != 'п':
            r['inflection']['family'] = 'pronominal'
    elif symbol in ('св', 'нсв', 'св-нсв'):
        r = reading('verb')
        r['verb'] = _verb(headword, symbol, grammar)
        if re.search(r'\bбезл\.', grammar):
            # Безличность представляется ограничениями позиций, а не
            # отдельной разновидностью основы: инфинитив остаётся доступным.
            for form in ('imperative', 'gerund', 'participle'):
                r['restrictions'].append(restriction({'form': form}, 'absent', 'безл.'))
            for person in (1, 2):
                r['restrictions'].append(restriction({'form': 'finite', 'person': person}, 'absent', 'безл.'))
            r['restrictions'].append(restriction({'form': 'finite', 'number': 'plural'}, 'absent', 'безл.'))
            for gender in ('masculine', 'feminine'):
                r['restrictions'].append(restriction({'form': 'finite', 'tense': 'past', 'gender': gender}, 'absent', 'безл.'))
            grammar = re.sub(r'\bбезл\.', '', grammar).strip(' ,')
        grammar = re.sub(r'\bнп\b', '', grammar).strip()
    elif symbol == 'н':
        r = reading('adverb')
    elif symbol in ('мс', 'числ.'):
        r = reading('pronoun' if symbol == 'мс' else 'numeral', None, 'unspecified')
    else:
        raise Unsupported(symbol, f'Неизвестный грамматический символ: {symbol!r}.')
    item['readings'].append(r)
    if r['part_of_speech'] == 'adverb':
        numeral = re.match(r'^числ\.,?\s*', grammar)
        if numeral:
            second = reading('numeral', None, 'unspecified')
            item['readings'].append(second)
            _parse_explicit(second, grammar[numeral.end():], headword)
        elif _remainder(grammar):
            raise Unsupported(_remainder(grammar))
        return
    if r['part_of_speech'] in ('pronoun', 'numeral'):
        _parse_explicit(r, grammar, headword)
        return
    reference = re.fullmatch(r'(спряж\.|склон\.)\s*см\.\s*(.+)', grammar)
    if reference:
        kind = 'conjugation_pattern' if reference[1] == 'спряж.' else 'declension_pattern'
        if kind == 'conjugation_pattern' and r['part_of_speech'] != 'verb':
            raise Unsupported(grammar)
        if kind == 'declension_pattern' and r['part_of_speech'] not in ('noun', 'adjective', 'surname'):
            raise Unsupported(grammar)
        target = word(reference[2].strip(' ;'))
        r['inflection']['kind'] = 'reference'
        r['reference'] = {'kind': kind, 'target': target, 'resolution': 'missing', 'source_index': None}
        item['status'] = 'needs_reference'
        return
    parts = re.split('[△Δ]', grammar, maxsplit=1)
    regular = parts[0].strip(' ,;')
    if len(parts) == 2:
        irregular = parts[1].strip()
        # Индексированная статья дополняется исключениями, а Δa без номера
        # означает полностью нерегулярное спряжение с выписанными основами.
        if not regular and r['part_of_speech'] == 'verb':
            match = re.match(r'^([abc])?\s*:?\s*(.*)$', irregular, re.S)
            r['inflection']['stress']['full'] = match[1] or 'a'
            irregular = match[2]
        else:
            _parse_regular(r, regular)
        special.exceptions(r, irregular)
    else:
        _parse_regular(r, regular)


def parse_article(item: dict) -> None:
    try:
        parse_description(item)
    except Unsupported as exc:
        if exc.fragment:
            item['unparsed'].append(exc.fragment)
        diagnose(item, 'unsupported', 'UNSUPPORTED_GRAMMAR', exc.message)
    except WordError as exc:
        item['readings'] = []
        diagnose(item, 'invalid', 'INVALID_INPUT', str(exc))
    # Отсутствие ударения не объявляется безударностью и не маскируется схемой a.
    missing = any(a['basis'] == 'missing' for a in item['headword']['accent_variants'])
    changing = any(r['part_of_speech'] != 'adverb' and r['inflection']['index'] != 0
                   for r in item['readings'])
    if missing and changing and item['status'] in ('parsed', 'needs_reference'):
        item['readings'] = []
        item['diagnostics'] = []
        diagnose(item, 'invalid', 'MISSING_STRESS',
                 'Не указано основное ударение многосложного изменяемого слова.')
