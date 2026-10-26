"""Построение именных и глагольных парадигм из модели разбора."""
from copy import deepcopy
from itertools import product
import json
import re

from .declension import (CASES, DeclensionError, decline, prepare, secondary_positions, V)
from .conjugation import Conjugator, ConjugationError, prepare_verb
from .model import reading as new_reading
from .references import ReferenceError, generation_order, transfer


class _RelationsError(ValueError):
    pass


def _features(reading):
    pos = reading['part_of_speech']
    numbers = ['plural'] if reading['number_scope'] == 'plural_only' else ['singular', 'plural']
    for number in numbers:
        genders = reading['agreement_genders'] if pos in ('adjective', 'surname') and number == 'singular' else [None]
        for gender in genders:
            for case in CASES:
                f = {'case': case, 'number': number}
                if pos == 'adjective': f['form'] = 'full'
                if gender or pos == 'noun' and reading['gender']:
                    f['gender'] = gender or reading['gender']
                animacies = ['inanimate', 'animate'] if pos == 'adjective' and case == 'accusative' else [None]
                for animacy in animacies:
                    yield {**f, **({'animacy': animacy} if animacy else {})}
    if pos == 'adjective':
        for gender in reading['agreement_genders']:
            yield {'form': 'short', 'number': 'singular', 'gender': gender}
        yield {'form': 'short', 'number': 'plural'}
        yield {'form': 'comparative'}


def _restriction(reading, features):
    matching = [r for r in reading['restrictions'] if all(features.get(k) == v for k, v in r['selector'].items())]
    if not matching:
        return 'normal', ''
    severity = {'tentative': 0, 'difficult': 1, 'absent': 2}
    selected = max(matching, key=lambda r: (len(r['selector']), severity[r['status']]))
    return selected['status'], selected['note']


def render_word(word):
    """Только представление уже вычисленной формы, без нового определения ударения."""
    variant = word['accent_variants'][0]
    marks = {p: '\u0300' for p in variant['secondary']}
    marks.update({p: '\u0301' for p in variant['primary']})
    result = word['text']
    for pos, mark in sorted(marks.items(), reverse=True):
        if word['text'][pos - 1].lower() != 'ё':
            result = result[:pos] + mark + result[pos:]
    return result


def _form(features, word, status='normal', note=''):
    return {'features': deepcopy(features), 'word': deepcopy(word),
            'stressed': render_word(word) if word is not None else None,
            'status': status, 'note': note}


def _computed_word(stem, text, primary):
    if primary and (not 0 < primary <= len(text) or text[primary - 1].lower() not in V):
        raise DeclensionError('Правило дало ударение не на гласной; форма не выдаётся.')
    secondary = secondary_positions(stem, text)
    if primary in secondary:
        secondary.remove(primary)
    if any(c.lower() == 'ё' and i + 1 not in [primary, *secondary] for i, c in enumerate(text)):
        raise DeclensionError('Получилась безударная ё: требуется указание чередования ё/е.')
    basis = ('yo' if primary and text[primary - 1].lower() == 'ё' else 'explicit' if primary
             else 'unstressed' if stem.accent_basis == 'unstressed' else 'missing')
    return {'text': text.upper() if stem.uppercase else text, 'accent_variants': [
        {'primary': [primary] if primary else [], 'secondary': secondary, 'basis': basis}]}


def _unique(forms):
    seen, result = set(), []
    for form in forms:
        key = json.dumps(form, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(form)
    return result


def _regular(headword, reading):
    paragraphs = set(reading['inflection'].get('paragraphs', []))
    if paragraphs - {3, 7, 8, 9, 10, 11}:
        raise DeclensionError('Не реализован именной параграф: ' + ', '.join(map(str, sorted(paragraphs - {3, 7, 8, 9, 10, 11}))))
    if 3 in paragraphs and reading['number_scope'] != 'plural_only':
        raise DeclensionError('§3 требует словарной пометы мн. и явно заданного образца.')
    if paragraphs & {7, 8, 9, 10, 11} and reading['part_of_speech'] != 'adjective':
        raise DeclensionError('§7–§11 относятся к прилагательным.')
    if 7 in paragraphs or 10 in paragraphs or 11 in paragraphs:
        reading = deepcopy(reading)
        selector = {'form': 'short'}
        if 7 in paragraphs:
            reading['restrictions'].append({'selector': selector, 'status': 'difficult', 'note': '§7: краткие формы прилагательного обычно избегаются.'})
        if 11 in paragraphs:
            reading['restrictions'].append({'selector': selector.copy(), 'status': 'difficult', 'note': '§11: регулярные краткие формы почти не употребляются; слова со сдвигом ударения рассматриваются отдельно.'})
        if 10 in paragraphs:
            selector['number'] = 'singular'
            genders = ['feminine', 'neuter'] if re.search('[^аеёиоуыэюя]лый$', headword['text']) else ['masculine', 'feminine', 'neuter']
            for gender in genders:
                reading['restrictions'].append({'selector': {**selector, 'gender': gender}, 'status': 'difficult', 'note': '§10: краткая форма совпадает с прошедшим временем глагола.'})
    required = {d['number'] for d in reading['deviations'] if not d['optional']}
    optional = sorted({d['number'] for d in reading['deviations'] if d['optional']})
    if (required | set(optional)) - {1, 2}:
        raise DeclensionError('В именном склонении реализованы отклонения ① и ②.')
    deviation_sets = [required | {n for n, enabled in zip(optional, bits) if enabled}
                      for bits in product((False, True), repeat=len(optional))]
    stems = [prepare(headword, reading, accent) for accent in headword['accent_variants']]
    forms = []
    for features in _features(reading):
        status, note = _restriction(reading, features)
        if status == 'absent':
            forms.append(_form(features, None, 'absent', note))
            continue
        replacements = _overrides(reading, features)
        if replacements:
            for replacement in replacements:
                for accent in replacement['word']['accent_variants']:
                    word = {**replacement['word'], 'accent_variants': [accent]}
                    forms.append(_form(features, word, status if status != 'normal' else replacement['status'], note or replacement['note']))
            continue
        # Местоименные и неизменяемые прилагательные не имеют кратких форм
        # и сравнительной степени по регулярной модели.
        unavailable = features.get('form') in ('short', 'comparative') and (
            reading['inflection']['family'] == 'pronominal' or reading['inflection']['index'] == 0)
        generated = []
        if not unavailable:
            for stem in stems:
                for deviations in deviation_sets:
                    generated.extend((stem, text, ac) for text, ac in decline(stem, reading, features, deviations))
        if not generated:
            forms.append(_form(features, None, 'absent', 'Форма не образуется по данному типу склонения.'))
        else:
            for stem, text, ac in generated:
                forms.append(_form(features, _computed_word(stem, text, ac), status, note))
    for spec in reading['inflection'].get('extra_cases', []):
        if reading['part_of_speech'] != 'noun' or reading['number_scope'] == 'plural_only' or reading['inflection']['index'] == 0:
            raise DeclensionError('П2/Р2 требуют изменяемого существительного с единственным числом.')
        sources = [f for f in forms if f['features'].get('case') == 'dative' and f['features'].get('number') == 'singular']
        for source in sources:
            features = {**source['features'], 'case': spec['case']}
            if spec['preposition']: features['preposition'] = spec['preposition']
            note = 'П2' if spec['case'] == 'locative' else 'Р2'
            if spec['optional']: note += ', факультативно'
            word = deepcopy(source['word'])
            if word and spec['case'] == 'locative':
                text = word['text'].replace('ё', 'е').replace('Ё', 'Е')
                primary = len(text)
                word = _computed_word(stems[0], text, primary)
            status, limit_note = _restriction(reading, features)
            if source['status'] == 'absent' or status == 'absent':
                forms.append(_form(features, None, 'absent', limit_note or source['note']))
            else:
                forms.append(_form(features, word, status if status != 'normal' else source['status'], note))
        if spec['case'] == 'locative' and spec['optional']:
            for source in list(forms):
                if source['features'].get('case') == 'prepositional' and source['features'].get('number') == 'singular':
                    features = {**source['features'], 'case': 'locative'}
                    if spec['preposition']: features['preposition'] = spec['preposition']
                    forms.append(_form(features, source['word'], source['status'], 'П2, факультативно'))
    return _unique(forms)


def _overrides(reading, features):
    """Исключение в И./Р. переносится в равный ему В., если В. не выписан."""
    explicit = reading['explicit_forms']
    match = lambda f, selector: all(selector.get(k) == v for k, v in f['features'].items())
    found = [f for f in explicit if match(f, features)]
    if not found and features.get('number') == 'plural' and features.get('case') in ('instrumental', 'prepositional'):
        source = [f for f in explicit if match(f, {**features, 'case': 'dative'})]
        for f in source:
            for accent in f['word']['accent_variants']:
                value = deepcopy(f)
                value['features'] = deepcopy(features)
                value['word']['accent_variants'] = [deepcopy(accent)]
                t = value['word']['text']
                if not t.endswith('м'): raise DeclensionError('Нерегулярный Д. мн. не позволяет вывести Т./П. мн.')
                value['word']['text'] = t + 'и' if features['case'] == 'instrumental' else t[:-1] + 'х'
                found.append(value)
    if found or features.get('case') != 'accusative': return found
    number = features.get('number')
    gender = reading['inflection']['pattern_gender'] or reading['gender']
    if number == 'singular' and gender == 'feminine': return []
    animate = features.get('animacy', reading['animacy']) == 'animate'
    case = 'genitive' if animate and (number == 'plural' or reading['gender'] == 'masculine') else 'nominative'
    return [f for f in explicit if match(f, {**features, 'case': case})]


def _explicit(headword, reading):
    forms = []
    for explicit in reading['explicit_forms']:
        for accent in explicit['word']['accent_variants']:
            word = {**explicit['word'], 'accent_variants': [accent]}
            forms.append(_form(explicit['features'], word, explicit['status'], explicit['note']))
    pending = list(reading['relations'])
    # Равенства могут ссылаться на другие равенства, а не только на исходные
    # формы. Если прогресса нет, это пропущенная зависимость или цикл.
    while pending:
        next_pending, progress = [], False
        for rel in pending:
            sources = []
            complete = True
            for selector in rel['same_as']:
                matching = [f for f in forms if all(f['features'].get(k) == v for k, v in selector.items())]
                if not matching:
                    complete = False
                    break
                sources.extend(matching)
            if not complete:
                next_pending.append(rel)
                continue
            forms.extend({**deepcopy(form), 'features': {**form['features'], **rel['target']}} for form in sources)
            progress = True
        if not progress:
            raise _RelationsError('Не удалось разрешить равенства выписанных форм: отсутствует источник или есть цикл.')
        pending = next_pending
    for limit in reading['restrictions']:
        selector = limit['selector']
        if not any(all(f['features'].get(k) == v for k, v in selector.items()) for f in forms):
            if limit['status'] == 'absent':
                forms.append(_form(selector, None, 'absent', limit['note']))
    for form in forms:
        status, note = _restriction(reading, form['features'])
        if status == 'absent':
            form.update(word=None, stressed=None, status=status, note=note)
        elif status != 'normal':
            form.update(status=status, note=note)
    return _unique(forms)


def _verb_positions():
    yield 'и', {'form': 'infinitive'}
    for code, gender in (('пем', 'masculine'), ('пеж', 'feminine'), ('пес', 'neuter'), ('пм', None)):
        yield code, {'form': 'finite', 'tense': 'past', 'number': 'singular' if gender else 'plural',
                     **({'gender': gender} if gender else {})}
    for prefix, tense in (('н', 'present'), ('б', 'future')):
        for number, n in (('singular', 'е'), ('plural', 'м')):
            for person in (1, 2, 3):
                yield prefix + str(person) + n, {'form': 'finite', 'tense': tense, 'number': number, 'person': person}
    for number, n in (('singular', 'е'), ('plural', 'м')):
        yield '!2' + n, {'form': 'imperative', 'number': number, 'person': 2}
    for code, tense in (('дн', 'present'), ('дп', 'past')):
        yield code, {'form': 'gerund', 'tense': tense}
    for code, tense, voice in (('чнд', 'present', 'active'), ('чпд', 'past', 'active'),
                                ('чнс', 'present', 'passive'), ('чпс', 'past', 'passive')):
        yield code, {'form': 'participle', 'tense': tense, 'voice': voice}


def _participle_reading(text, code, verb_reading):
    # У причастия собственная именная основа. Сравнительной степени нет,
    # краткие формы действительных причастий в исходнике помечены отсутствующими.
    r = new_reading('adjective')
    f = r['inflection']
    f.update(index=4 if code.endswith('д') else 1)
    f['stress']['full'] = 'a'
    if code == 'чпс':
        if text.endswith(('анный', 'янный', 'енный', 'ённый')):
            f['fleeting_vowel'] = True
            r['deviations'] = [{'number': 2, 'optional': False}]
            if text.endswith('ённый'):
                f['yo_alternation'] = True
                f['stress']['short'] = 'b'
        elif text.endswith('тый') and verb_reading['inflection']['stress']['past'] == 'c':
            f['stress']['short'] = 'c'
    return r


def _verbs(headword, reading):
    paragraphs = set(reading['inflection'].get('paragraphs', []))
    if paragraphs - {13, 14, 16}:
        raise ConjugationError('Не реализован глагольный параграф: ' + ', '.join(map(str, sorted(paragraphs - {13, 14, 16}))))
    alternatives = reading['inflection'].get('alternatives', [])
    if paragraphs & {13, 14} and ({reading['inflection']['index']} | {f['index'] for f in alternatives}) != {1, 6}:
        raise ConjugationError('§13/§14 требуют обеих явно заданных моделей 1 и 6.')
    required = {d['number'] for d in reading['deviations'] if not d['optional']}
    optional = sorted({d['number'] for d in reading['deviations'] if d['optional']})
    deviation_sets = [required | {n for n, enabled in zip(optional, bits) if enabled}
                      for bits in product((False, True), repeat=len(optional))]
    forms = []
    for accent in headword['accent_variants']:
        stem = prepare_verb(headword, reading, accent)
        for deviations in deviation_sets:
            conjugator = Conjugator(stem, reading, deviations, set(optional) - deviations)
            for code, features in _verb_positions():
                candidates = conjugator.forms(code)
                if features['form'] != 'participle':
                    status, limit_note = _restriction(reading, features)
                    for text, ac, state, note in candidates:
                        state = 'absent' if status == 'absent' or state == 'absent' else status if status != 'normal' else state
                        forms.append(_form(features, None if state == 'absent' else _computed_word(stem, text, ac), state, limit_note or note))
                    continue
                # Полные формы имеют case, краткие — только number/gender.
                for text, ac, state, note in candidates:
                    r = _participle_reading(text or '', code, reading)
                    base_word = _computed_word(stem, text, ac) if text else None
                    nominal_stem = prepare(base_word, r, base_word['accent_variants'][0]) if base_word else None
                    for nominal in _features(r):
                        if nominal['form'] == 'comparative': continue
                        short = nominal['form'] == 'short'
                        position = {**features, **{k: v for k, v in nominal.items() if k != 'form'}}
                        status, limit_note = _restriction(reading, position)
                        absent = state == 'absent' or status == 'absent' or short and code.endswith('д')
                        if absent:
                            forms.append(_form(position, None, 'absent', limit_note or note or 'Краткие формы действительных причастий не образуются.'))
                            continue
                        values = decline(nominal_stem, r, nominal, {d['number'] for d in r['deviations']})
                        for word, primary in values:
                            # Побочное ударение уже перенесено на основу причастия.
                            forms.append(_form(position, _computed_word(nominal_stem, word, primary),
                                               status if status != 'normal' else state, limit_note or note))
    if alternatives:
        # Альтернативный индекс описывает то же заглавное слово. Ограничения
        # и пометы статьи сохраняются, а основы готовятся независимо.
        for alternative in alternatives:
            r = deepcopy(reading)
            r['inflection'] = deepcopy(alternative)
            r['inflection'].pop('alternatives', None)
            forms.extend(_verbs(headword, r))
        if paragraphs & {13, 14}:
            # Пометы вариантов зависят от типа: их добавляем отдельным
            # проходом с известным происхождением формы, без угадывания текста.
            marked = []
            for pattern in [reading['inflection'], *alternatives]:
                r = deepcopy(reading)
                r['inflection'] = deepcopy(pattern)
                r['inflection'].pop('alternatives', None)
                r['inflection'].pop('paragraphs', None)
                for form in _verbs(headword, r):
                    f = form['features']
                    if form['status'] != 'absent':
                        if 13 in paragraphs and pattern['index'] == 1 and (f.get('form') == 'finite' and f.get('tense') in ('present', 'future') or f.get('form') == 'participle' and f.get('tense') == 'present'):
                            form['note'] = 'разг.'
                        if 14 in paragraphs and pattern['index'] == 6 and (f.get('form') == 'imperative' or f.get('form') == 'gerund' and f.get('tense') == 'present'):
                            form['note'] = 'устар.'
                    marked.append(form)
            forms = marked
    if 16 in paragraphs:
        if reading['inflection']['index'] != 4 or reading['inflection']['stress']['full'] != 'a' or not headword['text'].lower().endswith('ить'):
            raise ConjugationError('§16 требует глагола типа 4a на -ить.')
        variant = deepcopy(headword)
        variant['text'] = variant['text'][:-3] + ('АТЬ' if variant['text'].isupper() else 'ать')
        r = deepcopy(reading)
        r['inflection'].pop('paragraphs', None)
        r['inflection']['index'] = 1
        r['explicit_forms'] = []
        for form in _verbs(variant, r):
            f = form['features']
            if (f.get('form') == 'finite' and f.get('tense') in ('present', 'future')
                    or f.get('form') == 'imperative' or f.get('form') in ('gerund', 'participle') and f.get('tense') == 'present'):
                forms.append(form)
    return _unique(forms)


def generate_analyzed(analyses: list[dict]) -> list[dict]:
    """Дополняет результат analyze полем generation, не изменяя исходную модель."""
    output = deepcopy(analyses)
    for article_index in generation_order(output):
        article = output[article_index]
        generation = {'status': 'blocked', 'readings': [], 'diagnostics': []}
        article['generation'] = generation
        if article['status'] != 'parsed':
            generation['diagnostics'].append({'code': 'ANALYSIS_INCOMPLETE',
                'message': 'Генерация заблокирована: описание не разобрано полностью или требует образца.'})
            continue
        for index, reading in enumerate(article['readings']):
            item = {'reading_index': index, 'status': 'generated', 'forms': [], 'diagnostics': []}
            generation['readings'].append(item)
            try:
                kind = reading['inflection']['kind']
                if kind == 'reference':
                    item['forms'] = transfer(article, reading, output)
                elif reading['part_of_speech'] == 'verb':
                    item['forms'] = _verbs(article['headword'], reading)
                elif kind == 'invariable':
                    for accent in article['headword']['accent_variants']:
                        word = {**article['headword'], 'accent_variants': [accent]}
                        item['forms'].append(_form({}, word))
                elif kind == 'explicit':
                    item['forms'] = _explicit(article['headword'], reading)
                else:
                    item['forms'] = _regular(article['headword'], reading)
                if reading['verb'] and reading['verb']['partner']:
                    from .aspect import generate_partner
                    item['aspect_partner'] = generate_partner(article['headword'], reading, item['forms'])
            except (DeclensionError, _RelationsError) as exc:
                item.update(status='blocked', forms=[])
                item['diagnostics'].append({'code': 'REFERENCE_UNSUPPORTED' if isinstance(exc, ReferenceError) else 'CONJUGATION_UNSUPPORTED' if isinstance(exc, ConjugationError)
                    or reading['part_of_speech'] == 'verb' else 'DECLENSION_UNSUPPORTED', 'message': str(exc)})
        statuses = {r['status'] for r in generation['readings']}
        generation['status'] = ('generated' if statuses == {'generated'} else 'partial' if 'generated' in statuses
                                else 'not_implemented' if statuses == {'not_implemented'} else 'blocked')
        if generation['status'] == 'generated' and any(r.get('aspect_partner', {}).get('status') == 'blocked' for r in generation['readings']):
            generation['status'] = 'partial'
    return output


def generate(payload: dict | list[dict]) -> list[dict]:
    """Разбирает исходный JSON-объект/массив и строит поддержанные словоформы."""
    from . import analyze
    return generate_analyzed(analyze(payload))
