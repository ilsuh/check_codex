"""Основы и спряжение глаголов по типам Зализняка 1–16.

Адаптация Lingua/RU/Zaliz/Inflect.pm, коммит
5235199c09ab9e4443aeb7dd0b4d1be299cf80e8.
Copyright (C) 1999–2003 Juri Linkov. GNU GPL v2, см. THIRD_PARTY.md.
Внутренние короткие коды соответствуют позициям исходного алгоритма;
наружу модуль возвращает именованные признаки через generation.py.
"""
from dataclasses import dataclass
import re

from .declension import (V, C, SH, DeclensionError, first_vowel, last_vowel,
                         stress_code, substitute)


class ConjugationError(DeclensionError):
    """Описание не позволяет безопасно построить глагольную парадигму."""


def alternate(base, explicit=None):
    if explicit:
        if not base or base[-1] not in C:
            raise ConjugationError('Указанное согласное чередование неприменимо к основе.')
        return base[:-1] + explicit
    return substitute(base, [(r'([бпвфм])$', r'\1л'), (r'с[тк]$', 'щ'),
                            *[(c + '$', d) for c, d in zip('зсдтгкх', 'жшжчжчш')]])


@dataclass(frozen=True)
class VerbStem:
    lemma: str
    base: str
    first: str
    third: str
    infinitive_base: str
    index: int
    primary: int
    secondary: tuple[int, ...]
    accent_basis: str
    uppercase: bool
    reflexive: bool
    first_ending: str
    plural_ending: str
    third_ending: str


def prepare_verb(headword, reading, accent):
    f = reading['inflection']
    index, scheme = f['index'], f['stress']['full']
    irregular = index is None and bool(reading['explicit_forms'])
    if f['family'] != 'verbal' or index not in range(1, 17) and not irregular:
        raise ConjugationError('Нужен тип спряжения 1–16.')
    if scheme not in ('a', 'b', 'c', "c'"):
        raise ConjugationError('Для личных форм поддержаны схемы a, b, c, c\u2032.')
    if f['stress']['past'] not in (None, 'a', 'b', 'c', "c'", "c''"):
        raise ConjugationError('Не поддержана указанная схема ударения прошедшего времени.')
    lemma = headword['text']
    if not re.fullmatch('[А-Яа-яЁё]+', lemma) or len(accent['primary']) != 1:
        raise ConjugationError('Нужно простое глагольное заглавное слово с основным ударением.')
    upper = lemma.isupper()
    if upper:
        lemma = lemma.lower()
    # Возвратный постфикс не участвует в выделении инфинитивной основы.
    base = re.sub('с[яь]$', '', lemma)
    if bool(reading['verb']['reflexive']) != (base != lemma):
        raise ConjugationError('Признак возвратности не согласуется с заглавным словом.')
    inf = re.sub('[тч][ьи]$', '', base)
    if irregular:
        return VerbStem(lemma, base, base, base, inf, 0, accent['primary'][0],
                        tuple(accent['secondary']), accent['basis'], upper,
                        reading['verb']['reflexive'], 'ю', 'ю', 'е')
    patterns = {
        1: [('ть$', '')], 2: [('овать$', 'у'), (rf'([{SH}ц])евать$', r'\1у'), ('евать$', 'ю')],
        3: [('уть$', '')], 4: [('ить$', '')], 5: [('[аяе]ть$', '')],
        6: [('[ая]ть$', '')], 7: [('([зс])т[иь]$', r'\1')], 8: [('чь$', '')],
        9: [('ереть$', 'р')], 10: [('(о[лр])оть$', r'\1')], 11: [('ить$', 'ь')],
        12: [('греть$', 'гре'), ('петь$', 'по'), ('брить$', 'бре'), ('ыть$', 'о'), ('уть$', 'у'), ('ить$', 'и')],
        13: [('авать$', 'а')], 14: [('[ая]ть$', '')], 15: [('ть$', 'н')], 16: [('ть$', 'в')],
    }
    if not any(re.search(p, base, re.I) for p, _ in patterns[index]):
        raise ConjugationError(f'Окончание инфинитива не соответствует типу {index}.')
    third = substitute(base, patterns[index])
    if not third:
        raise ConjugationError('После выделения основы не осталось букв.')
    if f['special_alternation'] and index not in (3, 6):
        raise ConjugationError('Специальное чередование поддержано в глагольных типах 3 и 6.')
    first = third
    alt = f['consonant_alternation']
    if index in (8, 14) and not alt:
        raise ConjugationError(f'Для типа {index} необходимо явное указание согласного чередования.')
    if index in (4, 5):
        first = alternate(third, alt)
    elif index == 6 and not f['special_alternation']:
        first = third = alternate(third, alt)
    elif index == 7 and alt:
        first = third = alternate(third, alt)
    elif index in (8, 14):
        first = third + alt
        third = first[:-1] + {'г': 'ж', 'к': 'ч'}.get(first[-1], first[-1]) if index == 8 else first
    elif alt:
        raise ConjugationError('Согласное чередование неприменимо к указанному типу.')
    second = index in (4, 5)
    e1, ep, e3 = 'ю', 'я' if second else 'ю', 'и' if second else 'е'
    if index in (3, 7, 8, 9, 14, 15, 16):
        e1 = ep = 'у'
    elif index in (4, 5):
        if third[-1:] in SH: e1, ep = 'у', 'а'
        if first[-1:] in SH: e1 = 'у'
    elif index == 6 and (third[-1:] in SH or f['special_alternation']):
        e1 = ep = 'у'
    return VerbStem(lemma, base, first, third, inf, index, accent['primary'][0],
                    tuple(accent['secondary']), accent['basis'], upper,
                    reading['verb']['reflexive'], e1, ep, e3)


class Conjugator:
    """Один набор основ и отклонений; кэш зависимых форм локален парадигме."""
    def __init__(self, stem, reading, deviations, inactive_optional=()):
        self.s, self.r, self.d = stem, reading, deviations
        self.inactive_optional = set(inactive_optional)
        self.cache = {}
        self.overrides = verb_exceptions(reading)

    def forms(self, code):
        if code not in self.cache:
            self.cache[code] = self._forms(code)
        return self.cache[code]

    def _forms(self, code):
        s, r, d = self.s, self.r, self.d
        i, a = s.index, s.primary
        f, verb = r['inflection'], r['verb']
        full = stress_code(f['stress']['full'])
        scheme = full
        imperfective = verb['aspect'] in ('imperfective', 'biaspectual')
        perfective = verb['aspect'] in ('perfective', 'biaspectual')
        if code == 'и':
            return [(s.lemma, a, 'normal', '')]
        if code in self.overrides:
            return self.overrides[code]
        if (code.startswith('н') and not imperfective or code.startswith('б') and not perfective):
            return [(None, None, 'absent', 'Простая личная форма этого времени не образуется по виду глагола.')]
        # У полностью нерегулярного глагола незаданные основы не подменяются
        # инфинитивом: сначала используются связи выписанных форм.
        if i == 0 and code in ('чнд', 'дн', 'чнс', 'чпс'):
            return [(None, None, 'absent', 'Причастие или деепричастие не задано в нерегулярной статье.')]
        if i == 0 and code not in ('чпд', 'дп'):
            raise ConjugationError(f'В нерегулярной статье не задана позиция {code}.')
        present_active = code == 'чнд'
        if code == 'дн' and not (imperfective and i in (1, 2, 4, 5, 6, 7, 10, 12, 13, 16)):
            return [(None, None, 'absent', 'Деепричастие настоящего времени не образуется по этому типу.')]
        if present_active and not imperfective:
            return [(None, None, 'absent', 'У совершенного вида нет причастия настоящего времени.')]
        if code in ('чнс', 'чпс'):
            allowed = verb['transitivity'] == 'transitive' and not s.reflexive
            if code == 'чнс':
                allowed = allowed and imperfective and (full == 'a' and i in (1, 2, 12)
                    or i in (4, 5, 7, 13) or i == 6 and (s.base.endswith('ять') or f['special_alternation']))
            else:
                allowed = allowed and not (imperfective and verb['partner'])
            if not allowed:
                return [(None, None, 'absent', 'Страдательное причастие не образуется по виду, переходности или указанию видовой пары.')]
        base, end, ac, ae, note = '', '', None, False, ''
        if code[:1] in ('н', 'б'):
            p = code[1:]
            base = s.first if p == '1е' or p == '3м' and i not in (4, 5) else s.third
            end = {'1е': s.first_ending, '2е': s.third_ending + 'шь', '3е': s.third_ending + 'т',
                   '1м': s.third_ending + 'м', '2м': s.third_ending + 'те', '3м': s.plural_ending + 'т'}[p]
            ae = p == '1е' or full == 'c1' and p.endswith('м')
        elif code.startswith('п'):
            base = s.infinitive_base
            if i in (7, 8): base = re.sub('[тд]$', '', s.first)
            elif i == 9: base = re.sub('е$', '', base)
            elif i == 3 and f['special_alternation'] and (5 not in d or code != 'пем'):
                base = re.sub('ну$', '', base)
            scheme = stress_code(f['stress']['past'])
            end = '' if base[-1:] in C else 'л'
            if code != 'пем':
                base += 'л'
                end = {'пеж': 'а', 'пес': 'о', 'пм': 'и'}[code]
                ae = code == 'пеж'
        elif code.startswith('!'):
            base = s.infinitive_base if i == 13 else s.first if i not in (4, 5) else s.third
            if base[-1:] in V:
                end = 'и' if i == 4 and (full != 'a' or base.startswith('вы')) else 'й'
            else:
                end = 'и' if full != 'a' or base.startswith('вы') or re.search(rf'[{C}]ь?[{C}]$', base) or base.endswith('щ') else 'ь'
            if i == 11: base, end = re.sub('ь$', 'е', base), 'й'
            if 2 in d: end = 'й' if base[-1:] in V else 'ь'
            if 3 in d: end = 'и' if code == '!2е' else 'ь'
            if 3 in self.inactive_optional: end = 'ь'
            ae = True
        elif code == 'чнд':
            base, end, ae = s.third, s.plural_ending + 'щий', i in (4, 5)
        elif code == 'дн':
            base = s.infinitive_base if i == 13 else s.third
            end = 'а' if base[-1:] in SH else 'я'
            if i == 13: ac = a
            else: ae = True
        elif code in ('чпд', 'дп'):
            parent = self.forms('пем' if code == 'чпд' else 'чпд')[0]
            base, ac = re.sub('с[яь]$', '', parent[0]), parent[1]
            if code == 'чпд':
                base, end = re.sub('л$', 'в', base), 'ший'
                if i == 7 and s.base.endswith('сти') and f['consonant_alternation'] in ('т', 'д'):
                    base = s.first
                if (1 in d or 1 in self.inactive_optional) and i != 9: ac = a
                if 6 in d and not re.search('нув?', base): base = re.sub('в?$', 'нув', base)
            else:
                base = re.sub('й$', '', base)
        elif code == 'чнс':
            base = s.infinitive_base if i == 13 else s.third
            end = s.third_ending + 'мый'
            if i == 13: ac = a
            else: ae = i in (4, 5)
        elif code == 'чпс':
            if i != 14 and re.search('[ая]ть$', s.base):
                base, end, ac = s.infinitive_base, 'нный', a
                ac = self._previous_if_final_vowel(s.base, a)
            elif i == 4 or i == 5 and s.base.endswith('еть'):
                base, end = s.first, 'енный'
                if i == 5: ac = self._previous_if_final_vowel(s.infinitive_base, a)
            elif i == 1 and s.base.endswith(('одолеть', 'печатлеть')):
                base, end = s.base[:-3], 'ённый'
                ac = len(base) + 1
            elif i in (7, 8):
                base, end, scheme = s.third, 'енный', stress_code(f['stress']['past'])
            elif i in (3, 10):
                base, end = s.infinitive_base, 'тый'
                ac = self._previous_if_final_vowel(base, a)
            elif i in (9, 11, 12, 14, 15, 16):
                parent = self.forms('пем')[0]
                base = re.sub('л$', '', re.sub('с[яь]$', '', parent[0]))
                ac, end = parent[1], 'тый'
            else:
                return [(None, None, 'absent', 'Страдательное причастие не образуется по этому типу.')]
            if 7 in d and re.search(rf'[{V}]нный$', base + end):
                ac = len(base) + 1 if end == 'енный' else len(base)
                end = re.sub('^е', 'ё', end)
            if 8 in d:
                vowels = [n + 1 for n, c in enumerate(base + end) if c in V]
                if len(vowels) >= 3: ac = vowels[-3]
        else:
            raise ConjugationError(f'Неизвестная позиция спряжения: {code}.')
        if ac is None:
            ac = a
            if scheme == 'a' or scheme.startswith('c') and not ae:
                if ac >= len(base): ac = last_vowel(base)
            else:
                ac = len(base) + first_vowel(end) if first_vowel(end) else last_vowel(base)
                end = re.sub('^е', 'ё', end)
                if code == 'чнс' and base[-1:] in C: end = re.sub('^ё', 'о', end)
        text = base + end
        if (1 in d and (code in ('пем', 'пес', 'пм', 'чнс', 'чпс')) or 4 in d and code == 'чнд'):
            ac = last_vowel(text[:ac - 1]) or ac
        if f.get('yo_alternation') and (code.startswith('п') or code in ('чпд', 'чпс', 'дп')):
            yo = len(s.base[:-5]) + 1 if i == 9 and s.base.endswith('ереть') else s.base.rfind('е') + 1
            if yo == ac and text[ac - 1:ac] == 'е': text = text[:ac - 1] + 'ё' + text[ac:]
        if f['fleeting_vowel']:
            # Вставка о в приставке перед стечением согласных.
            pattern = (rf'^(во|в|и|ни|пора|ра)[зс]([{C}][ь{C}].*)' if re.match('^(во|в|и|ни|пора|ра)[зс]', text)
                       else rf'^(в|над|об|от|под|пред|с)([{C}][ь{C}].*)')
            match = re.match(pattern, text, re.I)
            if match:
                prefix = match[1] + ('зо' if '[зс]' in pattern else 'о')
                text = prefix + match[2]
                if ac > len(match[1]): ac += 1
        if code == '!2м': text += 'те'
        if s.reflexive: text += 'сь' if text[-1:] in V else 'ся'
        result = [(text, ac, 'normal', note)]
        if code == 'дп':
            if 9 in d:
                present = self.forms('дн')[0]
                if present[0] is None:
                    # Отклонение ⑨ разрешает эту форму и у совершенного вида.
                    base2 = s.infinitive_base if i == 13 else s.third
                    end2 = 'а' if base2[-1:] in SH else 'я'
                    ac2 = a if full == 'a' else len(base2) + 1
                    present = (base2 + end2 + ('сь' if s.reflexive else ''), ac2, 'normal', '')
                result = [present, (text, ac, 'normal', 'устар.')]
            if i == 9 and not s.reflexive and perfective:
                result.insert(0, (re.sub('ть$', 'в', s.lemma), a, 'normal', ''))
            # Невозвратные формы на -вши допускают вариант на -в.
            if text.endswith('вши'): result.insert(0, (text[:-2], ac, 'normal', 'устар.' if 9 in d else note))
        if scheme in ('c1', 'c2') and code in ('пем', 'пеж', 'пес', 'пм'):
            if scheme == 'c1' and code == 'пес' or scheme == 'c2' and code != 'пеж':
                result.append((text, last_vowel(text), 'normal', 'устар.' if code == 'пем' else ''))
        return result

    @staticmethod
    def _previous_if_final_vowel(text, accent):
        vowels = [n + 1 for n, c in enumerate(text) if c in V]
        return vowels[-2] if len(vowels) >= 2 and accent == vowels[-1] else accent


def verb_exceptions(reading):
    """Связи исключений get_all_wi: зависимые формы строятся до спряжения.

    Благодаря этому исключение прошедшего времени влияет на причастие,
    а выписанное причастие — на деепричастие и именное склонение.
    """
    result = {}
    for form in reading['explicit_forms']:
        f = form['features']
        code = None
        if f.get('form') == 'finite':
            if f.get('tense') == 'past':
                code = 'пм' if f['number'] == 'plural' else 'пе' + {'masculine': 'м', 'feminine': 'ж', 'neuter': 'с'}[f['gender']]
            elif f.get('tense') in ('present', 'future'):
                code = ('н' if f['tense'] == 'present' else 'б') + str(f['person']) + ('е' if f['number'] == 'singular' else 'м')
        elif f.get('form') == 'imperative': code = '!2' + ('е' if f['number'] == 'singular' else 'м')
        elif f.get('form') == 'participle' and 'case' not in f and 'number' not in f:
            code = 'ч' + ('н' if f['tense'] == 'present' else 'п') + ('д' if f['voice'] == 'active' else 'с')
        elif f.get('form') == 'gerund': code = 'дн' if f['tense'] == 'present' else 'дп'
        if code:
            for accent in form['word']['accent_variants']:
                if len(accent['primary']) != 1 or accent['secondary']:
                    raise ConjugationError('Для нерегулярной глагольной основы требуется одно основное ударение без побочного.')
                result.setdefault(code, []).append((form['word']['text'], accent['primary'][0], form['status'], form['note']))
    def derived(target, source, change):
        if target not in result and source in result:
            result[target] = [change(text, ac, state, note) for text, ac, state, note in result[source]]
    for prefix in ('н', 'б'):
        if prefix + '1е' in result and prefix + '3е' in result:
            if not all(re.search('[еёию]т(с[ья])?$', t) for t, *_ in result[prefix + '3е']):
                # Из «дам, даст» нельзя получить «дашь, дадим, дадут»
                # заменой обычного окончания; эти формы должны быть выписаны.
                continue
            for suffix, end in (('2е', 'шь'), ('1м', 'м'), ('2м', 'те')):
                derived(prefix + suffix, prefix + '3е', lambda t, a, s, n, end=end:
                        (re.sub(r'т(с[ья])?$', lambda m: end + ('сь' if end == 'те' else 'ся') if m[1] else end, t), a, s, n))
            if prefix + '3м' not in result:
                values = []
                for j, (t, a, s, n) in enumerate(result[prefix + '3е']):
                    if re.search('[её]т(с[ья])?$', t):
                        t, a, s, n = result[prefix + '1е'][min(j, len(result[prefix + '1е']) - 1)]
                        t = re.sub(r'(с[ья])?$', lambda m: 'т' + ('ся' if m[1] else ''), t, count=1)
                    else:
                        t = re.sub(r'ит(с[ья])?$', lambda m: ('ат' if t[:m.start()].endswith(tuple(SH)) else 'ят') + (m[1] or ''), t)
                    values.append((t, a, s, n))
                result[prefix + '3м'] = values
            if '!2е' not in result:
                vals = []
                for t, a, s, n in result[prefix + '3м']:
                    reflexive = t.endswith(('ся', 'сь'))
                    root = re.sub('с[ья]$', '', t)[:-2]
                    if root[-1:] in V:
                        text, ac = root + 'й', min(a, last_vowel(root))
                    else:
                        text, ac = root + 'и', len(root) + 1
                    vals.append((text + ('сь' if text.endswith('и') else 'ся') if reflexive else text, ac, s, n))
                result['!2е'] = vals
            if reading['verb']['aspect'] in ('imperfective', 'biaspectual'):
                def present_form(t, a, s, n, ending):
                    reflexive = t.endswith(('ся', 'сь'))
                    root = re.sub('с[ья]$', '', t)
                    base = root[:-1] if ending == 'щий' else root[:-2]
                    first_ac = result[prefix + '1е'][0][1]
                    ac = first_ac if root.endswith(('ят', 'ат')) or ending != 'щий' else a
                    if ending != 'щий': ending = 'а' if base[-1:] in SH else 'я'
                    return base + ending + ('ся' if ending == 'щий' else 'сь') if reflexive else base + ending, ac, s, n
                derived('чнд', prefix + '3м', lambda t, a, s, n: present_form(t, a, s, n, 'щий'))
                derived('дн', prefix + '3м', lambda t, a, s, n: present_form(t, a, s, n, 'я'))
    derived('!2м', '!2е', lambda t, a, s, n: (re.sub('(с[ья])?$', lambda m: 'те' + ('сь' if m[1] else ''), t, count=1), a, s, n))
    for code, end in (('пес', 'о'), ('пм', 'и')):
        derived(code, 'пеж', lambda t, a, s, n, end=end: (re.sub('а(с[ья])?$', lambda m: end + (m[1] or ''), t), a, s, n))
    derived('чпд', 'пем', lambda t, a, s, n: (re.sub('л$', 'в', re.sub('с[ья]$', '', t)) + 'ший' + ('ся' if reading['verb']['reflexive'] else ''), a, s, n))
    # Здесь сохраняются оба нормативных невозвратных окончания -в / -вши.
    if 'дп' not in result and 'чпд' in result:
        values = []
        for t, a, s, n in result['чпд']:
            t = re.sub('й(ся)?$', lambda m: 'сь' if m[1] else '', t)
            if t.endswith('вши'): values.append((t[:-2], a, s, n))
            values.append((t, a, s, n))
        result['дп'] = values
    return result
