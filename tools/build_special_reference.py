"""Контроль исключений и видовых партнёров по исходному Perl, без Python-движка."""
import argparse
import ast
import json
from pathlib import Path
import subprocess

from build_declension_reference import ROOT, COMMIT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    sha = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if sha != COMMIT: parser.error(f'Нужен коммит {COMMIT}.')
    rows = []
    for line in (checkout / 'zaliz.adb').read_bytes().decode('koi8-r').splitlines():
        wi = dict(f.partition(':')[::2] if ':' in f else (f, '') for f in line.split('\t'))
        if 'искл' in wi:
            try:
                # Только литералы доверенного файла. Произвольный Perl/Python
                # не исполняется при чтении ADB.
                wi['искл'] = ast.literal_eval(wi['искл'].lstrip(':').replace('=>', ':'))
            except (ValueError, SyntaxError): continue
        rows.append(wi)
    cases = [
        ('брат', 'мо', '1a △ мн. бра́тья; Р. мн. бра́тьев; Д. мн. бра́тьям'),
        ('друг', 'мо', '3c △ мн. друзья́; Р. мн. друзе́й; Д. мн. друзья́м'),
        ('не́бо', 'с', '1c △ мн. небеса́; Р. мн. небе́с; Д. мн. небеса́м'),
        ('ребёнок', 'мо', '3*a △ мн. де́ти; Р. мн. дете́й; Д. мн. де́тям; Т. мн. детьми́; П. мн. де́тях'),
        ('затоло́чь', 'св', '8b/b (-к-) △ буд. затолку́, затолчёт; прош. затоло́к, затолкла́; прич. действ. прош. затоло́кший; прич. страд. затолчённый'),
        ('бе́рег', 'м', '3c①, П2(на)'),
        ('лес', 'м', '1c①, П2(в)'),
        ('край', 'м', '6c①, П2(на)'),
    ]
    clean = lambda wi: {k: v for k, v in wi.items() if k not in ('вар', 'з', 'з2', 'з3', 'фр', 'до')}
    inputs, chosen = [], []
    for lemma, symbol, grammar in cases:
        text = lemma.replace('\u0301', '')
        wi = next(w for w in rows if w.get('с') == text)
        inputs.append({'lemma': lemma, 'symbol': symbol, 'grammar': grammar})
        chosen.append(clean(wi))
    run = lambda entries, extra=(): json.loads(subprocess.run(['perl', str(ROOT / 'tools/reference_declension.pl'), str(checkout), *extra],
        input=json.dumps(entries, ensure_ascii=False).encode(), capture_output=True, check=True).stdout)
    paradigms = run(chosen)
    output = []
    for source, wi, expected in zip(inputs, chosen, paradigms):
        output.append({'input': source, 'adb': wi, 'expected': expected})
    # Видовые указания представлены без словаря исключений: проверяется
    # формальная таблица I–III и арабские указания, а не поиск готовой леммы.
    partners = [w for w in rows if w.get('т') == 'г' and w.get('гпр') in ('I', 'II', 'III', 'I(-А-)', 'I(-О-)', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16')
                and set(w) <= set('с у т и у1 у2 ч ч2 ч3 чё ос осф гв гп гпр'.split()) and w.get('у', '').isdigit()]
    selected = []
    for typ in sorted({w['гпр'] for w in partners}):
        selected.extend([w for w in partners if w['гпр'] == typ][:3])
    expected_partners = run(selected, ['--partners'])
    partner_cases = []
    for wi, expected in zip(selected, expected_partners):
        lemma, ac = wi['с'], int(wi['у'])
        marked = lemma if lemma[ac - 1] == 'ё' else lemma[:ac] + '\u0301' + lemma[ac:]
        grammar = ('нп ' if wi['гп'] == 'нп' else '') + wi['и'] + ('°' if 'ч2' in wi else '*' if 'ч' in wi else '')
        grammar += wi['у1'].replace('1', "'").replace('2', "''")
        if 'у2' in wi: grammar += '/' + wi['у2'].replace('1', "'").replace('2', "''")
        if 'ч3' in wi: grammar += ' (-' + wi['ч3'] + '-)'
        if 'чё' in wi: grammar += ', ё'
        grammar += ''.join('①②③④⑤⑥⑦⑧⑨'[int(n) - 1] for n in wi.get('ос', ''))
        if 'осф' in wi: grammar += '[' + ''.join('①②③④⑤⑥⑦⑧⑨'[int(n) - 1] for n in wi['осф']) + ']'
        # В старой записи ударение помечено прописной гласной.
        p = wi['гпр'].replace('А', 'а\u0301').replace('О', 'о\u0301')
        grammar += ' ◑' + p
        case = {'input': {'lemma': marked, 'symbol': wi['гв'], 'grammar': grammar}, 'adb': wi,
                'expected': expected.replace("'", '\u0301')}
        # В оригинале односложные слова выводятся без графического ударения.
        if '\u0301' not in case['expected'] and 'ё' not in case['expected']:
            vowels = [i for i, c in enumerate(case['expected']) if c in 'аеёиоуыэюя']
            if len(vowels) == 1:
                pos = vowels[0] + 1
                case['expected'] = case['expected'][:pos] + '\u0301' + case['expected'][pos:]
        # Независимые языковые ожидания для дефекта старого регулярного
        # выражения: перед -ирать/-имать оно требует ещё одну гласную.
        corrected = {'впирать': 'впере́ть', 'впираться': 'впере́ться', 'втирать': 'втере́ть',
                     'вжимать': 'вжа́ть', 'вжиматься': 'вжа́ться', 'вминать': 'вмя́ть'}
        if wi['с'] in corrected and wi['гпр'] in ('9', '14'):
            case['expected_corrected'] = corrected[wi['с']]
            case['difference'] = 'В исходном regex перед -ирать/-имать требуется дополнительная гласная; исходная лемма ошибочно остаётся без преобразования.'
        partner_cases.append(case)
    path = ROOT / 'tests/fixtures/special.reference.json'
    path.write_text(json.dumps({'commit': COMMIT, 'cases': output, 'partners': partner_cases}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(output)} статей с исключениями/П2, {len(partner_cases)} видовых указаний.')


if __name__ == '__main__':
    main()
