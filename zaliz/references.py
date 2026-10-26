"""Разрешение отсылок после чтения группы, включая ссылки вперёд и циклы."""
from collections import defaultdict
from copy import deepcopy

from .declension import DeclensionError

from .model import diagnose


class ReferenceError(DeclensionError):
    """Образец найден, но его применение не определено однозначно."""


def generation_order(items):
    """Образец обрабатывается раньше зависимых статей без рекурсии Python."""
    done, order = set(), []
    for start in range(len(items)):
        path, seen = [], set()
        current = start
        while current not in done and current not in seen:
            seen.add(current)
            path.append(current)
            refs = [r['reference'] for r in items[current]['readings'] if r['reference'] and r['reference']['resolution'] == 'resolved']
            if not refs: break
            target = refs[0]['source_index']
            if not isinstance(target, int) or not 0 <= target < len(items): break
            current = target
        for node in reversed(path):
            if node not in done:
                done.add(node)
                order.append(node)
    return order


def transfer(article, reading, articles):
    """Перенос готовой парадигмы при замене приставки/начальной части.

    Общая конечная часть должна содержать гласную и хотя бы три буквы.
    Все формы должны сохранять заменяемое начало; иначе нужна отдельная
    инструкция преобразования. Такой случай не подменяется общей основой.
    """
    from .generation import _form, _restriction, _unique
    ref = reading['reference']
    index = ref['source_index']
    if ref['resolution'] != 'resolved' or not isinstance(index, int) or not 0 <= index < len(articles):
        raise ReferenceError('Не разрешена зависимость от образца.')
    target = articles[index]
    compatible = [(i, r) for i, r in enumerate(target['readings']) if r['part_of_speech'] == reading['part_of_speech']]
    if len(compatible) != 1:
        raise ReferenceError('В образце нет единственного совместимого разбора.')
    ri, pattern = compatible[0]
    for key in ('gender', 'animacy', 'number_scope'):
        if pattern[key] != reading[key]: raise ReferenceError(f'Различается признак образца {key}; требуется явное правило переноса.')
    if reading['verb']:
        for key in ('aspect', 'reflexive', 'transitivity'):
            if pattern['verb'][key] != reading['verb'][key]:
                raise ReferenceError(f'Различается глагольный признак {key}; требуется явное правило переноса.')
    generation = target.get('generation', {})
    source_readings = generation.get('readings', [])
    generated = next((r for r in source_readings if r['reading_index'] == ri), None)
    if not generated or generated['status'] != 'generated':
        raise ReferenceError('Генерация статьи-образца не завершена успешно.')
    local, original = article['headword'], target['headword']
    source, dest = original['text'], local['text']
    count = 0
    for a, b in zip(reversed(source.lower()), reversed(dest.lower())):
        if a != b: break
        count += 1
    suffix = source[-count:] if count else ''
    if count < 3 or not any(c.lower() in 'аеёиоуыэюя' for c in suffix):
        raise ReferenceError('Не выделена общая конечная часть образца длиной не менее трёх букв с гласной.')
    old, new = source[:-count], dest[:-count]
    if len(original['accent_variants']) != 1 or len(local['accent_variants']) != 1:
        raise ReferenceError('Для переноса образца нужно однозначное ударение обеих лемм.')
    oa, na = original['accent_variants'][0], local['accent_variants'][0]
    def relative(accent, prefix):
        return ([p - len(prefix) for p in accent['primary'] if p > len(prefix)],
                [p - len(prefix) for p in accent['secondary'] if p > len(prefix)])
    if relative(oa, old) != relative(na, new):
        raise ReferenceError('Ударения заглавных слов не соответствуют общему образцу.')
    for kind in ('primary', 'secondary'):
        if bool([p for p in oa[kind] if p <= len(old)]) != bool([p for p in na[kind] if p <= len(new)]):
            raise ReferenceError('Различается наличие ударения в заменяемом начале; требуется отдельное правило.')
    result = []
    for form in generated['forms']:
        f = deepcopy(form)
        word = f['word']
        if word:
            if word['text'][:len(old)].lower() != old.lower():
                raise ReferenceError('Форма образца изменяет заменяемое начало; перенос заблокирован.')
            tail = word['text'][len(old):]
            if dest.isupper(): tail = tail.upper()
            elif not new and dest[:1].islower(): tail = tail[:1].lower() + tail[1:]
            elif not new and dest[:1].isupper(): tail = tail[:1].upper() + tail[1:]
            word['text'] = new + tail
            for accent in word['accent_variants']:
                for kind in ('primary', 'secondary'):
                    values = []
                    for p in accent[kind]:
                        if p > len(old): values.append(p - len(old) + len(new))
                        else:
                            candidates = [n for n in na[kind] if n <= len(new)]
                            if len(candidates) != 1: raise ReferenceError('Не определён перенос ударения в заменяемой части.')
                            values.extend(candidates)
                    accent[kind] = sorted(set(values))
        status, note = _restriction(reading, f['features'])
        if status == 'absent': result.append(_form(f['features'], None, status, note))
        else: result.append(_form(f['features'], word, status if status != 'normal' and f['status'] != 'absent' else f['status'], note or f['note']))
    return _unique(result)


def resolve(items: list[dict]) -> None:
    index = defaultdict(list)
    for i, item in enumerate(items):
        if item['headword'] is not None and item['status'] in ('parsed', 'needs_reference'):
            for r in item['readings']:
                index[item['headword']['text']].append((i, r['part_of_speech']))
    refs, edges, outcomes = {}, {}, {}
    for i, item in enumerate(items):
        if item['status'] != 'needs_reference':
            if item['status'] == 'parsed':
                outcomes[i] = 'resolved'
            continue
        ref = next(r['reference'] for r in item['readings'] if r['reference'])
        refs[i] = ref
        target = ref['target']['text']
        expected_pos = 'verb' if ref['kind'] == 'conjugation_pattern' else None
        candidates = [j for j, pos in index[target]
                      if pos == expected_pos or expected_pos is None and pos in ('noun', 'adjective', 'surname')]
        if not candidates:
            outcomes[i] = 'missing'
        elif len(candidates) != 1:
            outcomes[i] = 'ambiguous'
        else:
            ref['source_index'] = candidates[0]
            edges[i] = candidates[0]
    # В текущей грамматике одна статья имеет не более одной отсылки.
    # Итеративный обход не зависит от ограничения рекурсии Python.
    for start in refs:
        path, positions = [], {}
        node = start
        while node not in outcomes:
            if node in positions:
                for cycle_node in path[positions[node]:]:
                    outcomes[cycle_node] = 'cycle'
                break
            positions[node] = len(path)
            path.append(node)
            node = edges[node]
        outcome = outcomes[node]
        for previous in reversed(path):
            outcomes.setdefault(previous, outcome)
    for i, ref in refs.items():
        state = outcomes[i]
        ref['resolution'] = state
        if state == 'resolved':
            items[i]['status'] = 'parsed'
            continue
        target = ref['target']['text']
        if state == 'missing':
            message = (f'В группе нет описания образца «{target}».' if i not in edges
                       else f'Описание образца «{target}» содержит неразрешённую отсылку.')
            code = 'MISSING_REFERENCE'
        elif state == 'ambiguous':
            message = f'Для образца «{target}» найдено несколько подходящих разборов.'
            code = 'AMBIGUOUS_REFERENCE'
        else:
            message = f'Циклическая отсылка к образцу «{target}».'
            code = 'REFERENCE_CYCLE'
        diagnose(items[i], 'needs_reference', code, message)
