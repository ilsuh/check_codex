"""Склонение имён по подготовленному описанию.

Адаптация правил и таблиц Lingua/RU/Zaliz/Inflect.pm, nlp-rus-zaliz,
коммит 5235199c09ab9e4443aeb7dd0b4d1be299cf80e8.
Copyright (C) 1999–2003 Juri Linkov. GNU GPL v2, см. LICENSE и THIRD_PARTY.md.
Вычисления выполняются над буквами Unicode, без Perl и словарной базы.
"""
from dataclasses import dataclass
from importlib.resources import files
import json
import re
from os.path import commonprefix

V = 'аеёиоуыэюя'
C = 'бвгджзйклмнпрстфхцчшщ'
C2 = 'бвгдзйклмнпрстфх'
SH = 'шжчщ'
GENDERS = {'masculine': 'м', 'feminine': 'ж', 'neuter': 'с'}
CASES = {'nominative': 'и', 'genitive': 'р', 'dative': 'д', 'accusative': 'в',
         'instrumental': 'т', 'prepositional': 'п'}
ENDINGS = json.loads(files('zaliz').joinpath('endings.json').read_text(encoding='utf-8'))


class DeclensionError(ValueError):
    """Описание разобрано, но правило генерации отсутствует или противоречиво."""


def first_vowel(text):
    return next((i + 1 for i, c in enumerate(text) if c.lower() in V), 0)


def last_vowel(text):
    return next((i + 1 for i in range(len(text) - 1, -1, -1) if text[i].lower() in V), 0)


def substitute(text, rules):
    # Применяется первое сработавшее чередование, а не все подряд.
    for pattern, replacement in rules:
        changed, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
        if count:
            if text[:1].isupper():
                changed = changed[:1].upper() + changed[1:]
            return changed
    return text


def stress_code(scheme):
    return (scheme or 'a').replace("''", '2').replace("'", '1')


def ending_stressed(scheme, p, gender, short=False):
    s = stress_code(scheme)
    if short:
        return not (s.startswith('a') or s.startswith('c') and not (p == 'ие' and gender == 'ж'))
    return not (s.startswith('a') or s == 'b1' and p == 'те'
                or s == 'c' and p.endswith('е') or s.startswith('d') and p.endswith('м')
                or s == 'd1' and p == 'ве' or s == 'e' and (p.endswith('е') or p == 'им')
                or s.startswith('f') and p == 'им' or s == 'f1' and p == 'ве'
                or s == 'f2' and p == 'те')


@dataclass(frozen=True)
class Stem:
    lemma: str
    base: str
    saved: str | None
    gender: str
    family: str
    index: int
    primary: int
    secondary: tuple[int, ...]
    accent_basis: str
    fleeting: bool
    special: bool
    full_stress: str
    short_stress: str | None
    yo: bool
    uppercase: bool
    reflexive: str = ''


def remove_fleeting(base, index, gender, pronominal):
    if pronominal or gender == 'м' or gender == 'ж' and index == 8:
        rules = [(rf'о([^{V}]+)$', r'\1'), (rf'и([^{V}]*)$', r'ь\1'),
                 (rf'([{V}])[её]([^{V}]+)$', r'\1й\2')]
        if index == 6 and (gender == 'м' or pronominal):
            rules.append((r'[её]$', 'ь'))
        if index == 3 and (gender == 'м' or pronominal):
            rules.append((rf'([{C2}])[её]([^{V}]+)$', r'\1ь\2'))
        rules += [(rf'л[её]([^{V}]+)$', r'ль\1'), (rf'[её]([^{V}]+)$', r'\1')]
        return substitute(base, rules)
    return base


def add_fleeting(base, index, accented):
    rules = [(r'ь$', 'е' if accented else 'и')] if index == 6 else []
    rules += [(r'[ьй]ц$', 'ец'), (rf'[ьй]([{C}])$', ('ё' if accented else 'е') + r'\1'),
              (rf'([кгх])([{C}])$', r'\1о\2'), (rf'([^{SH}ц])([кгх])$', r'\1о\2'),
              (r'ц$', 'ец')]
    if accented:
        rules.append((rf'([{SH}ц])([{C}])$', r'\1о\2'))
    rules.append((rf'([{C}])$', ('ё' if accented else 'е') + r'\1'))
    return substitute(base, rules)


def prepare(headword, reading, accent):
    f = reading['inflection']
    family, index = f['family'], f['index']
    lemma = headword['text']
    uppercase = lemma.isupper()
    if uppercase:
        lemma = lemma.lower()
    if ' ' in lemma or '-' in lemma:
        raise DeclensionError('Склонение составных заглавных слов ещё не реализовано.')
    if len(accent['primary']) > 1:
        raise DeclensionError('Одновременные основные ударения требуют разбора частей слова.')
    if family not in ('substantive', 'adjectival', 'pronominal'):
        raise DeclensionError(f'Не реализовано семейство склонения: {family}.')
    if index is None or not 0 <= index <= 8:
        raise DeclensionError('Не указан допустимый тип склонения.')
    full = f['stress']['full']
    supported_full = ('a', 'b', "b'", 'c', 'd', "d'", 'e', 'f', "f'", "f''") if family == 'substantive' else ('a', 'b')
    if index and full not in supported_full:
        raise DeclensionError('Не указана поддержанная основная схема ударения для этого семейства.')
    if f['stress']['short'] not in (None, 'a', "a'", 'b', "b'", 'c', "c'", "c''"):
        raise DeclensionError('Не реализована указанная схема ударения кратких форм.')
    if family == 'adjectival' and index not in (0, 1, 2, 3, 4, 5):
        raise DeclensionError('Адъективное склонение поддерживает типы 0–5; требуется уточнение образца.')
    gender = GENDERS.get(f['pattern_gender'] or reading['gender'], 'м')
    if not f['pattern_gender'] and family == 'substantive' and gender == 'м' and lemma.endswith(('а', 'я')):
        gender = 'ж'
    base, saved, reflexive = lemma, None, ''
    fleeting = f['fleeting_vowel'] or f['special_alternation'] and gender == 'м' and index == 3
    if reading['part_of_speech'] == 'surname':
        if index != 1 or family != 'pronominal' or not re.search(r'(?:ов|ев|ин)а?$', lemma):
            raise DeclensionError('Для фамилий реализован образец <мс 1a> на -ов/-ев/-ин.')
        base = re.sub('а$', '', lemma)
    elif family == 'adjectival':
        if base.endswith('ся'):
            base, reflexive = base[:-2], 'ся'
        base = base[:-2] if index else base
    elif fleeting and reading['number_scope'] != 'plural_only' and (base[-1].lower() not in V + 'йь' or base.endswith(('й', 'ь'))):
        base = re.sub('[йь]$', '', base)
        saved = base
        base = remove_fleeting(base, index, gender, family == 'pronominal')
    elif index:
        base = re.sub(rf'[{V}йь]$', '', base)
    return Stem(lemma, base, saved, gender, family, index,
                (accent['primary'] or [0])[0], tuple(accent['secondary']), accent['basis'], fleeting,
                f['special_alternation'], f['stress']['full'] or 'a', f['stress']['short'],
                f.get('yo_alternation', False), uppercase, reflexive)


def decline(stem, reading, features, deviations, *, short_scheme=None):
    """Возвращает пары (написание, основное ударение) для одной позиции."""
    if features.get('form') == 'comparative':
        p = 'с'
    elif features.get('form') == 'short':
        p = 'и' + ('м' if features['number'] == 'plural' else 'е')
    else:
        p = CASES[features['case']] + ('м' if features['number'] == 'plural' else 'е')
    short = features.get('form') == 'short'
    adjective = stem.family == 'adjectival'
    pronominal = stem.family == 'pronominal'
    g = GENDERS.get(features.get('gender'), stem.gender) if reading['part_of_speech'] in ('adjective', 'surname') else stem.gender
    animate = features.get('animacy') == 'animate' if 'animacy' in features else (
        reading['animacy'] == 'animate' or reading['inflection']['pattern_animacy'] == 'animate')
    # У одушевлённого мужского существительного с образцом среднего рода В.=Р.
    if p == 'ве' and (g in ('м', 'с')):
        masculine_animate = reading['gender'] == 'masculine' and reading['animacy'] == 'animate'
        p = 'ре' if g == 'м' and animate or masculine_animate else 'ие'
    if p == 'вм':
        p = 'рм' if animate else 'им'
    if stem.index == 0:
        return [(stem.lemma, stem.primary)]
    base, end, ac = stem.base, None, None
    group = 1 if stem.index in (1, 3, 4, 5) else 2 if stem.index in (2, 6, 7) else 8
    scheme = short_scheme or stem.short_stress or stem.full_stress if short else stem.full_stress
    ae = ending_stressed(scheme, p, g, short)
    fleeting = stem.fleeting
    if p == 'с':
        if pronominal:
            return []
        if base.endswith(('к', 'г', 'х')):
            base = base[:-1] + dict(zip('кгх', 'чжш'))[base[-1]]
            end, ac = 'е', last_vowel(base)
        else:
            end = 'ее'
            ae = not (stem.full_stress == 'a' and stem.short_stress is None)
    if stem.family == 'substantive' and stem.special and g == 'с' and stem.index == 8:
        if p == 'ие':
            return [(stem.lemma, stem.primary)]
        base += 'ен'
        if p.endswith('м'):
            group = 1
    if stem.family == 'substantive':
        if 1 in deviations and p == 'им':
            end = ('а' if group == 1 else 'я') if g == 'м' else ('ы' if stem.index in (1, 5) else 'и')
        elif 2 in deviations and p == 'рм':
            end = ('' if group == 1 else 'ь') if g == 'м' else ('ов' if group == 1 else 'ёв' if ae else 'ев') if g == 'с' else 'ей'
    elif adjective:
        if 1 in deviations and short and g == 'м' and p == 'ие':
            base = re.sub('н$', '', base)
            end, fleeting = '', False
        elif 2 in deviations:
            if short:
                base = re.sub('н$', '', base)
                fleeting = False
            elif p == 'с':
                ac = stem.primary
    if stem.family == 'substantive' and end is None:
        if stem.index == 4 and p == 'рм':
            end = 'ей' if g == 'м' or ae else ''
        if stem.index in (6, 7):
            if p == 'рм':
                end = ('ёв' if ae else 'ев') if g == 'м' else 'й'
            if stem.index == 7 and (p == 'де' and g == 'ж' or p == 'пе'):
                end = 'е' if ae else 'и'
    if stem.family == 'substantive' and stem.special and g == 'м':
        if stem.index == 1 and p.endswith('м'):
            base = re.sub('ин$', '', base)
            if p == 'им': end = 'е'
            elif p == 'рм': end = ''
            if stem.full_stress == 'a' and len(base) < stem.primary:
                ac = last_vowel(base)
        elif stem.index == 3 and p.endswith('м'):
            fleeting = False
            if re.search(r'[ёо]но?к$', base):
                base = re.sub('ёно?к$', 'ят', base)
                base = re.sub('оно?к$', 'ат', base)
                g, group = 'с', 1
            if re.search(r'[ёо]ноче?к$', base):
                base = re.sub('ёноче?к$', 'ятк', base)
                base = re.sub('оноче?к$', 'атк', base)
                g, group = 'ж', 1
            if p == 'рм': base = re.sub('тк$', 'ток', base)
    if pronominal and short:
        return []
    # Особые окончания притяжательных имён на -ов/-ин, включая фамилии.
    if pronominal and stem.index == 1 and g in ('м', 'с') and re.search('(ов|ев|ин)$', base):
        end = {'ре': 'а', 'де': 'у', 'пе': 'е'}.get(p, end)
    if end is None:
        family = 'к' if short else 'м' if pronominal else 'а' if adjective else 'с'
        key = family + g + str(group) + ('о' if animate else 'н') + ('у' if ae else 'б')
        try:
            end = ENDINGS[key][p]
        except KeyError as exc:
            raise DeclensionError(f'Нет таблицы окончания для {key}/{p}.') from exc
        if stem.index in (3, 4): end = re.sub('^ы', 'и', end)
        if stem.index in (4, 5) and not ae: end = re.sub('^о', 'е', end)
        if stem.index in (6, 7): end = end.replace('ь', 'й')
        if stem.index == 8 and stem.base.endswith(tuple(SH + 'ц')): end = re.sub('^я', 'а', end)
    if fleeting and re.fullmatch(r'(й|ью?)?', end):
        if stem.saved is not None:
            base = stem.saved
        else:
            base = add_fleeting(base, stem.index, ae)
            if stem.index == 2 and stem.full_stress == 'a' and end == 'ь' and (g == 'ж' and stem.lemma.endswith('ня') or stem.lemma.endswith('ний')):
                end = ''
    if ac is None:
        if not ae:
            if stress_code(stem.full_stress).startswith(('a', 'c', 'e')) or stress_code(stem.full_stress) == 'b1':
                ac = stem.primary
            elif stem.full_stress.startswith('f'):
                ac = first_vowel(base)
            else:
                vowels = [i + 1 for i, ch in enumerate(base) if ch.lower() in V]
                ac = vowels[-2] if fleeting and re.fullmatch(r'(й|ью?)?', end) and len(vowels) > 1 else last_vowel(base)
        elif pronominal and re.fullmatch('[ое]г[о]|[ое]му', end):
            ac = len(base) + len(end)
        else:
            ac = len(base) + first_vowel(end) if first_vowel(end) else last_vowel(base)
    if stem.yo:
        if 0 < stem.primary <= len(base) and base[stem.primary - 1].lower() == 'ё' and ac != stem.primary:
            replacement = 'Е' if base[stem.primary - 1].isupper() else 'е'
            base = base[:stem.primary - 1] + replacement + base[stem.primary:]
        if 0 < ac <= len(base) and (p == 'рм' or not re.search('.е', base[ac - 1:])):
            base = base[:ac - 1] + base[ac - 1].translate(str.maketrans('еЕ', 'ёЁ')) + base[ac:]
    text = base + end + stem.reflexive
    forms = [(text, ac)]
    if g == 'ж' and p == 'те' and text.endswith('й'):
        forms.append((text[:-1] + 'ю', ac))
    if p == 'с' and text.endswith('ее'):
        forms.append((text[:-1] + 'й', ac))
    s = stress_code(scheme)
    if short and short_scheme is None:
        if (s == 'a1' and g == 'ж' and p == 'ие' or s == 'c1' and p == 'им'
                or s == 'c2' and (g == 'с' and p == 'ие' or p == 'им')):
            forms += decline(stem, reading, features, deviations, short_scheme='b')
        elif s == 'b1' and p == 'им':
            forms = decline(stem, reading, features, deviations, short_scheme='a') + forms
    return list(dict.fromkeys(forms))


def secondary_positions(stem, text):
    if not stem.secondary:
        return []
    # Сохраняем только доказанно неизменившуюся часть основы. Подбор похожих
    # букв после изменения основы не доказывает соответствие слогов.
    normalize = str.maketrans('ёЁ', 'еЕ')
    unchanged = len(commonprefix((stem.lemma.translate(normalize), text.translate(normalize))))
    if any(pos > unchanged for pos in stem.secondary):
        raise DeclensionError('Правило переноса побочного ударения через изменение основы ещё не определено.')
    return list(stem.secondary)
