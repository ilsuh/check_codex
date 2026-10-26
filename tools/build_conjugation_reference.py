"""Независимая выборка глагольных парадигм оригинального Perl-генератора.

python3 tools/build_conjugation_reference.py /путь/nlp-rus-zaliz
Python-генератор не импортируется. Эталоны содержат исходную структуру ADB,
чтобы соответствие современного описания исходным признакам было проверяемым.
"""
import argparse
import json
from pathlib import Path
import random
import re
import subprocess

from build_declension_reference import COMMIT, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'tests/fixtures/conjugation.reference.json')
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    sha = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if sha != COMMIT: parser.error(f'Нужен коммит {COMMIT}.')
    allowed = set('с у т и у1 у2 ч ч2 ч3 чё ос осф гв гп гпр гбл вар з з2 з3 фр'.split())
    candidates = []
    for line in (checkout / 'zaliz.adb').read_bytes().decode('koi8-r').splitlines():
        wi = dict(field.partition(':')[::2] if ':' in field else (field, ':') for field in line.split('\t'))
        if wi.get('т') != 'г' or set(wi) - allowed: continue
        if not wi['и'].isdigit() or not 1 <= int(wi['и']) <= 16: continue
        if not wi['у'].isdigit() or not re.fullmatch('[а-яё]+', wi['с']): continue
        primary = int(wi['у'])
        if not 0 < primary <= len(wi['с']) or wi['с'][primary - 1] not in 'аеёиоуыэюя': continue
        # Видовой партнёр влияет на отсутствие страдательного причастия;
        # римские указания имеют прямое представление в новом формате.
        if 'гпр' in wi and not re.fullmatch('I{1,3}', wi['гпр']): continue
        lemma = wi['с']
        if lemma[primary - 1] != 'ё': lemma = lemma[:primary] + '\u0301' + lemma[primary:]
        grammar = ('нп ' if wi['гп'] == 'нп' else '') + wi['и']
        grammar += '°' if 'ч2' in wi else '*' if 'ч' in wi else ''
        grammar += wi['у1'].replace('1', "'").replace('2', "''")
        if 'у2' in wi: grammar += '/' + wi['у2'].replace('1', "'").replace('2', "''")
        if 'ч3' in wi: grammar += ' (-' + wi['ч3'] + '-)'
        grammar += ''.join('①②③④⑤⑥⑦⑧⑨'[int(n) - 1] for n in wi.get('ос', ''))
        if 'осф' in wi: grammar += '[' + ''.join('①②③④⑤⑥⑦⑧⑨'[int(n) - 1] for n in wi['осф']) + ']'
        if 'чё' in wi: grammar += ', ё'
        if 'гбл' in wi: grammar += ', безл.'
        if 'гпр' in wi: grammar += ' ◑' + wi['гпр']
        source = {'lemma': lemma, 'symbol': wi['гв'], 'grammar': grammar}
        original = {k: v for k, v in wi.items() if k not in ('з', 'з2', 'з3', 'фр', 'вар')}
        candidates.append((source, original))
    random.Random(2026).shuffle(candidates)
    cases = []
    for index in range(1, 17):
        cases.extend([r for r in candidates if r[1]['и'] == str(index)][:8])
    for key in ('у1', 'у2', 'ос', 'осф', 'ч3', 'чё', 'ч', 'ч2', 'гв', 'гбл'):
        for value in sorted({r[1][key] for r in candidates if key in r[1]}):
            row = next(r for r in candidates if r[1].get(key) == value)
            if row not in cases: cases.append(row)
    raw = subprocess.run(['perl', str(ROOT / 'tools/reference_declension.pl'), str(checkout)],
        input=json.dumps([wi for _, wi in cases], ensure_ascii=False).encode(), capture_output=True, check=True)
    results = json.loads(raw.stdout)
    fresh = subprocess.run(['perl', str(ROOT / 'tools/reference_declension.pl'), str(checkout), '--fresh-optional'],
        input=json.dumps([wi for _, wi in cases], ensure_ascii=False).encode(), capture_output=True, check=True)
    fresh_results = json.loads(fresh.stdout)
    output = []
    for (source, wi), result, raw_result in zip(cases, fresh_results, results):
        slots = {}
        for code, variants in result.items():
            values = []
            for form in variants:
                status = {'фн': 'absent', 'фз': 'difficult', 'фп': 'tentative'}.get(form.get('ф'), 'normal')
                text = form['с'] if status != 'absent' else None
                value = {'text': text, 'primary': int(form['у']) if text else None, 'status': status,
                         'note': form.get('з', '') if text else ''}
                if value not in values: values.append(value)
            slots[code] = values
        case = {'input': source, 'adb': wi, 'expected': slots}
        if 'осф' in wi:
            case['reference_mode'] = 'fresh_optional_branches'
            case['original_unmodified_result'] = raw_result
        output.append(case)
    args.output.write_text(json.dumps({'source': 'https://github.com/jurta/nlp-rus-zaliz',
        'commit': COMMIT, 'seed': 2026, 'cases': output}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Сохранено {len(output)} статей, {sum(len(c["expected"]) for c in output)} позиций.')


if __name__ == '__main__':
    main()
