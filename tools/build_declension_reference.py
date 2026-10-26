"""Получение эталонов только от оригинала, без импорта Python-генератора.

python3 tools/build_declension_reference.py /путь/nlp-rus-zaliz
Используются исходные данные KOI8-R и фиксированная выборка. Перезапись эталона
явная; в обычном тестировании этот скрипт не запускается.
"""
import argparse
import json
from pathlib import Path
import random
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '5235199c09ab9e4443aeb7dd0b4d1be299cf80e8'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkout', type=Path)
    p.add_argument('--output', type=Path, default=ROOT / 'tests/fixtures/declension.reference.json')
    args = p.parse_args()
    checkout = args.checkout.resolve()
    sha = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if sha != COMMIT:
        p.error(f'Для воспроизводимости нужен коммит {COMMIT}; получен {sha}')
    allowed = set('с у т т2 р рм о и у1 у2 ч ч2 чё ос осф мн фн фз фп вар з з2 з3 фр'.split())
    candidates = []
    for line in (checkout / 'zaliz.adb').read_bytes().decode('koi8-r').splitlines():
        if line.startswith('#'):
            continue
        wi = {}
        for field in line.split('\t'):
            key, sep, value = field.partition(':')
            wi[key] = value if sep else ':'
        if set(wi) - allowed or wi.get('т') not in ('с', 'п'):
            continue
        if wi.get('о') not in (None, 'н', 'о') or wi.get('рм') and wi['рм'] != wi.get('р'):
            # Несовпадающие роды проверяются отдельными современными примерами.
            continue
        if not wi.get('и', '').isdigit() or not 1 <= int(wi['и']) <= 8 or not wi.get('у', '').isdigit():
            continue
        if wi.get('мн') not in (None, ':') or wi.get('т2') not in (None, 'п', 'мс'):
            continue
        if wi.get('т2') == 'мс' and wi['и'] == '1':
            # У оригинала не реализованы особые Р./Д./П. притяжательных на -ов/-ин.
            continue
        if wi.get('у1') not in ('a', 'b', 'b1', 'c', 'd', 'd1', 'e', 'f', 'f1', 'f2') or wi.get('у2', 'a') not in ('a', 'a1', 'b', 'b1', 'c', 'c1', 'c2'):
            continue
        if any(set(wi.get(k, '')) - {'1', '2'} for k in ('ос', 'осф')):
            continue
        if wi.get('фп') or wi.get('фз') not in (None, '^к') or wi.get('фн') not in (None, '^с', '^к.ем'):
            continue
        if wi.get('фн') == '^к.ем' and wi.get('фз') != '^к':
            continue
        lemma, primary = wi['с'], int(wi['у'])
        if not re.fullmatch('[а-яё]+', lemma) or not 0 < primary <= len(lemma) or lemma[primary - 1] not in 'аеёиоуыэюя':
            continue
        marked = lemma if lemma[primary - 1] == 'ё' else lemma[:primary] + '\u0301' + lemma[primary:]
        grammar = wi['и'] + ('°' if 'ч2' in wi else '*' if 'ч' in wi else '') + wi['у1'].replace('1', "'").replace('2', "''")
        if 'у2' in wi:
            grammar += '/' + wi['у2'].replace('1', "'").replace('2', "''")
        grammar += ''.join('①②'[int(n) - 1] for n in wi.get('ос', ''))
        if 'осф' in wi:
            grammar += '[' + ''.join('①②'[int(n) - 1] for n in wi['осф']) + ']'
        if 'чё' in wi: grammar += ', ё'
        if wi.get('фн') == '^к.ем': grammar += '⌧'
        elif wi.get('фз') == '^к': grammar += '✕'
        if wi.get('фн') == '^с': grammar += '~'
        symbol = wi.get('р', 'м') + ('о' if wi.get('о') == 'о' else '') if wi['т'] == 'с' else 'п'
        if 'мн' in wi:
            grammar = '<' + symbol + ' ' + grammar + '>'
            symbol = 'мн.'
        elif 'т2' in wi:
            grammar = '<' + wi['т2'] + ' ' + grammar + '>'
        source = {'lemma': marked, 'symbol': symbol, 'grammar': grammar}
        # Исключаем только семантические метаданные, не влияющие на эту парадигму.
        actual_wi = {k: v for k, v in wi.items() if k not in ('з', 'з2', 'з3', 'фр', 'вар')}
        candidates.append((source, actual_wi))
    random.Random(2026).shuffle(candidates)
    cases = []
    for pos in ('с', 'п'):
        cases.extend([row for row in candidates if row[1]['т'] == pos][:150])
    # Добавляем представителей редких типов независимо от частотности выборки.
    for i in range(1, 9):
        row = next((r for r in candidates if r[1]['т'] == 'с' and int(r[1]['и']) == i), None)
        if row and row not in cases: cases.append(row)
    # Частотная выборка в основном содержит схему a. Явно добавляем редкие
    # акцентные схемы и чередования, чтобы они действительно проверялись.
    groups = [(pos, key, value) for pos in ('с', 'п')
              for key in ('у1', 'у2', 'ч2', 'ос', 'осф', 'чё', 'мн')
              for value in sorted({r[1][key] for r in candidates if r[1]['т'] == pos and key in r[1]})]
    for pos, key, value in groups:
        row = next((r for r in candidates if r[1]['т'] == pos and r[1].get(key) == value), None)
        if row and row not in cases: cases.append(row)
    raw = subprocess.run(['perl', str(ROOT / 'tools/reference_declension.pl'), str(checkout)],
        input=json.dumps([wi for _, wi in cases], ensure_ascii=False).encode(), capture_output=True, check=True)
    results = json.loads(raw.stdout)
    output = []
    status_map = {'фн': 'absent', 'фз': 'difficult', 'фп': 'tentative'}
    for (source, wi), result in zip(cases, results):
        slots = {}
        for code, variants in result.items():
            if 'мн' in wi and code.endswith('е'):
                continue
            values = []
            for form in variants:
                status = status_map.get(form.get('ф'), 'normal')
                text = form['с'] if status != 'absent' else None
                accent = int(re.match(r'\d+', str(form.get('у') or '0'))[0]) if text is not None else None
                value = {'text': text, 'primary': accent, 'status': status}
                if value not in values: values.append(value)
            slots[code] = values
        output.append({'input': source, 'adb': wi, 'expected': slots})
    args.output.write_text(json.dumps({'source': 'https://github.com/jurta/nlp-rus-zaliz',
        'commit': COMMIT, 'seed': 2026, 'cases': output}, ensure_ascii=False, indent=2) + '\n')
    print(f'Сохранено {len(output)} статей, {sum(len(c["expected"]) for c in output)} позиций парадигм.')


if __name__ == '__main__':
    main()
