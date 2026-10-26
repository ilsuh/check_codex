"""Видовой партнёр — новое слово, отдельно от парадигмы исходного глагола.

Правила verb_opposite из Inflect.pm (Juri Linkov, GNU GPL v2).
Неприменимое формальное указание не выдаётся как успешно построенное слово.
"""
import re
from types import SimpleNamespace

from .declension import V, SH, first_vowel, last_vowel, secondary_positions, DeclensionError
from .text import word
from .model import WordError


class AspectError(DeclensionError):
    pass


def _replace(text, pattern, replacement):
    changed, count = re.subn(pattern + '$', replacement, text)
    if not count: raise AspectError('Видовое указание не соответствует конечной части слова.')
    return changed


def _replacement(raw):
    if raw is None: return None, None
    raw = raw.strip()
    if not raw.startswith('-'): raise AspectError('Не распознано указание замены видового партнёра.')
    middle = raw.endswith('-')
    value = raw[1:-1] if middle else raw[1:]
    value = word(value)
    if len(value['accent_variants']) != 1: raise AspectError('Замена видового партнёра неоднозначна по ударению.')
    return ('middle' if middle else 'suffix'), value


def _build(headword, reading, first):
    partner = reading['verb']['partner']
    typ = partner['type']
    acs = headword['accent_variants']
    if len(acs) != 1 or len(acs[0]['primary']) != 1:
        raise AspectError('Видовой партнёр требует одного основного ударения.')
    original, a = headword['text'], acs[0]['primary'][0]
    text = re.sub('с[яь]$', '', original.lower())
    reflexive = reading['verb']['reflexive']
    replace_kind, replacement = _replacement(partner['replacement'])
    if typ in ('I', 'II', 'III'):
        if reading['verb']['aspect'] != 'perfective': raise AspectError('Римское указание требует совершенного исходного вида.')
        if replace_kind == 'suffix': raise AspectError('Для римского указания реализована только замена корневой гласной.')
        if typ == 'I':
            final = a == last_vowel(text)
            if re.search('(?:[ао]ть|нуть)$', text) and not text.endswith('ьнуть'):
                text = re.sub('(?:[ао]ть|нуть)$', 'ивать' if re.search('[' + SH + 'кгх](?:[ао]ть|нуть)$', text) else 'ывать', text)
            elif re.search('(?:ять|ьнуть)$', text):
                text = re.sub('(?:ять|ьнуть)$', 'ивать', text)
            else:
                if first is None: raise AspectError('Для видового указания нужна форма будущего 1 лица ед. числа.')
                text, a = first
                text = re.sub('с[яь]$', '', text.lower())
                final = a == last_vowel(text)
                text = _replace(text, '[ую]', 'ивать' if text.endswith('ю') or re.search('[' + SH + 'кгх]у$', text) else 'ывать')
            if text.startswith('вы') or final:
                vowels = [n + 1 for n, c in enumerate(text) if c in V]
                if len(vowels) < 3: raise AspectError('Не найден третий слог с конца у видового партнёра.')
                a = vowels[-3]
            if replacement:
                if len(replacement['text']) != 1 or replacement['text'] not in V:
                    raise AspectError('Замена корневой гласной должна содержать одну гласную.')
                text = text[:a - 1] + replacement['text'] + text[a:]
            if reading['inflection'].get('yo_alternation'):
                text = text[:a - 1] + 'ё' + text[a:]
        elif typ == 'II':
            if text.endswith('нуть'): text = text[:-4] + 'ать'
            elif not text.endswith('ать'):
                if first is None: raise AspectError('Для ◑II нужна форма будущего 1 лица ед. числа.')
                text, a = first
                text = re.sub('с[яь]$', '', text.lower())
                text = _replace(text, '[ую]', 'ять' if text.endswith('ю') else 'ать')
            a = last_vowel(text)
            if replacement: raise AspectError('Замена гласной при ◑II ещё не определена.')
        else:
            text = _replace(text, 'нуть' if text.endswith('нуть') else 'ть', 'вать')
            a = last_vowel(text)
            if replacement: raise AspectError('Замена гласной при ◑III ещё не определена.')
    elif typ.isdigit() and 1 <= int(typ) <= 16:
        if reading['verb']['aspect'] != 'imperfective': raise AspectError('Числовое указание требует несовершенного исходного вида.')
        t = int(typ)
        previous_vowel = lambda s: last_vowel(s[:last_vowel(s) - 1])
        if re.search('[ыи]вать$', text) and a < len(text) - 4:
            if t in (1, 5, 6): text = _replace(text, '[ыи]вать', 'ать' if text.endswith('ывать') or re.search('[' + SH + 'кгх]ивать$', text) else 'ять')
            elif t == 2:
                if text.endswith('цовывать') and a == len(text) - 6: text = text[:-8] + 'цевать'; a = last_vowel(text)
                elif text.endswith('овывать') and a == len(text) - 6: text = text[:-7] + 'овать'; a = last_vowel(text)
                elif text.endswith('ёвывать'): text = text[:-7] + 'евать'; a = last_vowel(text)
                else: raise AspectError('◑2 не соответствует суффиксу и ударению.')
            elif t == 3: text = _replace(text, '[ыи]вать', 'нуть')
            elif t == 4: text = _replace(text, '[ыи]вать', 'ить')
            elif t == 7: text = _replace(text, 'зывать' if text.endswith('зывать') else '[тдсб]ывать', 'зть' if text.endswith('зывать') else 'сть')
            elif t == 8: text = _replace(text, '[кг]ивать', 'чь')
            elif t == 10:
                if a != len(text) - 6: raise AspectError('◑10 не соответствует ударению.')
                text = _replace(text, 'алывать' if text.endswith('алывать') else 'арывать', 'олоть' if text.endswith('алывать') else 'ороть')
                a = last_vowel(text)
            else: raise AspectError('Не определено сочетание суффикса с числовым видовым указанием.')
        elif re.search('[ая]ть$', text) and not text.endswith('вать') and a == len(text) - 2:
            if t in (1, 5, 6): a = previous_vowel(text)
            elif t in (3, 4):
                a = previous_vowel(text)
                text = _replace(text, '[ая]ть', 'нуть' if t == 3 else 'ить')
            elif t == 7:
                a = previous_vowel(text)
                text = _replace(text, 'зать' if text.endswith('зать') else '[тдсб]ать', 'зть' if text.endswith('зать') else 'сть')
            elif t == 8:
                a = previous_vowel(text)
                text = _replace(text, '[кг]ать', 'чь')
            elif t == 9: text = _replace(text, 'ирать', 'ереть'); a = last_vowel(text)
            elif t == 14:
                text = _replace(text, 'и[мн]ать', 'ать' if re.search('[' + SH + ']и[мн]ать$', text) else 'ять')
                a -= 2
            else: raise AspectError('Не определён переход к указанному типу от -ать/-ять.')
        elif text.endswith('вать') and a == len(text) - 2:
            if t not in (1, 3, 5, 6, 11, 12, 13, 15, 16): raise AspectError('Не определён переход к указанному типу от -вать.')
            a = previous_vowel(text)
            text = text[:-4] + ('нуть' if t == 3 else 'ть')
        else:
            raise AspectError('Форма исходного слова не соответствует таблице видовых указаний.')
        if replacement:
            repl = replacement['text']
            ra = replacement['accent_variants'][0]
            if replace_kind == 'middle':
                if len(repl) != 1 or repl not in V: raise AspectError('Нужна одна корневая гласная.')
                m = re.search(r'([' + V + r'][^' + V + r']*)(?:[аяеи]ть|нуть|чь)$', text)
                if not m: raise AspectError('Не определена позиция корневой замены.')
                text = text[:m.start()] + repl + text[m.start() + 1:]
                if ra['basis'] in ('explicit', 'yo'): a = m.start() + 1
            elif re.fullmatch('[аяи]ть|нуть', repl):
                if ra['basis'] in ('explicit', 'yo'):
                    a = len(text) - len(repl) + ra['primary'][0]
            else:
                length = len(repl) + 1 if re.search('[бпвфм]ить$', repl) or original.lower().endswith('ждать') else len(repl) - 1 if re.search('о?стить$', repl) else len(repl)
                text = text[:-length] + repl
                if ra['basis'] in ('explicit', 'yo'): a = len(text) - len(repl) + ra['primary'][0]
        if text.startswith('вы'): a = 2
    else:
        raise AspectError('Не поддержан тип видового указания.')
    if original.lower()[acs[0]['primary'][0] - 1] == 'ё' and a != acs[0]['primary'][0]:
        p = acs[0]['primary'][0] - 1
        if text[p:p + 1] == 'ё': text = text[:p] + 'е' + text[p + 1:]
    if reflexive: text += 'сь' if text.endswith('ти') else 'ся'
    if not 0 < a <= len(text) or text[a - 1] not in V:
        raise AspectError('Не определено корректное ударение видового партнёра.')
    if original.isupper(): text = text.upper()
    elif original[:1].isupper(): text = text[:1].upper() + text[1:]
    secondary = secondary_positions(SimpleNamespace(lemma=original, secondary=acs[0]['secondary']), text)
    marked = text[:a] + '\u0301' + text[a:]
    output = word(marked)
    output['accent_variants'][0]['secondary'] = secondary
    if len(output['accent_variants']) != 1: raise AspectError('Получилось противоречивое ударение с ё.')
    return output


def generate_partner(headword, reading, forms):
    from .generation import render_word
    p = reading['verb']['partner']
    result = {'status': 'generated', 'words': [], 'diagnostics': []}
    try:
        if p['type'] == 'explicit':
            normalized = word(p['replacement'])
            if any(a['basis'] == 'missing' for a in normalized['accent_variants']): raise AspectError('В выписанном видовом партнёре нужно ударение.')
            candidates = [{**normalized, 'accent_variants': [a]} for a in normalized['accent_variants']]
        else:
            firsts = [(f['word']['text'], f['word']['accent_variants'][0]['primary'][0]) for f in forms
                      if f['features'] == {'form': 'finite', 'tense': 'future', 'person': 1, 'number': 'singular'} and f['word']]
            candidates = [_build(headword, reading, first) for first in firsts or [None]]
        for candidate in candidates:
            item = {'word': candidate, 'stressed': render_word(candidate),
                    'aspect': 'perfective' if p['direction'] == 'to_perfective' else 'imperfective'}
            if item not in result['words']: result['words'].append(item)
    except (DeclensionError, WordError) as exc:
        result.update(status='blocked', words=[])
        result['diagnostics'].append({'code': 'ASPECT_PARTNER_UNSUPPORTED', 'message': str(exc)})
    return result
