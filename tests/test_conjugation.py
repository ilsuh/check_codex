"""Независимые глагольные эталоны и языковые примеры спряжения."""
import copy
from collections import Counter
import json
from pathlib import Path
import unittest

from zaliz import analyze, generate, generate_analyzed
from test_declension import code_selector as nominal_selector

ROOT = Path(__file__).resolve().parents[1]


def verb_selector(code):
    if '-' in code:
        prefix, nominal = code.split('-', 1)
        f = nominal_selector(nominal, 'п')
        del f['form']
        return {'form': 'participle', 'tense': 'present' if prefix[1] == 'н' else 'past',
                'voice': 'active' if prefix[2] == 'д' else 'passive', **f}
    if code == 'и': return {'form': 'infinitive'}
    if code in ('дн', 'дп'): return {'form': 'gerund', 'tense': 'present' if code == 'дн' else 'past'}
    if code.startswith('!'):
        return {'form': 'imperative', 'number': 'singular' if code[-1] == 'е' else 'plural', 'person': 2}
    if code.startswith(('н', 'б')):
        return {'form': 'finite', 'tense': 'present' if code[0] == 'н' else 'future',
                'person': int(code[1]), 'number': 'singular' if code[2] == 'е' else 'plural'}
    f = {'form': 'finite', 'tense': 'past', 'number': 'plural' if code == 'пм' else 'singular'}
    if code != 'пм': f['gender'] = {'м': 'masculine', 'ж': 'feminine', 'с': 'neuter'}[code[2]]
    return f


def matches(features, selector):
    # У краткого причастия нет case; простое подмножество признаков ошибочно
    # подмешало бы полные формы в ту же контрольную позицию.
    return features == selector


class VerbReferenceTests(unittest.TestCase):
    fixtures = json.loads((ROOT / 'tests/fixtures/conjugation.reference.json').read_text())['cases']

    def test_coverage(self):
        self.assertEqual({int(c['adb']['и']) for c in self.fixtures}, set(range(1, 17)))
        self.assertEqual(len(self.fixtures), 143)
        self.assertEqual(sum(len(c['expected']) for c in self.fixtures), 21307)


def register():
    for n, fixture in enumerate(VerbReferenceTests.fixtures):
        def test(self, fixture=fixture):
            result = generate(fixture['input'])[0]
            self.assertEqual(result['status'], 'parsed', result)
            g = result['generation']
            self.assertEqual(g['status'], 'generated', g)
            actual = g['readings'][0]['forms']
            for code, expected in fixture['expected'].items():
                selector = verb_selector(code)
                fs = [f for f in actual if matches(f['features'], selector)]
                values = {(f['word']['text'] if f['word'] else None,
                    (f['word']['accent_variants'][0]['primary'] or [0])[0] if f['word'] else None,
                    f['status'], f['note'] if f['word'] else '') for f in fs}
                wanted = {(f['text'], f['primary'], f['status'], f['note']) for f in expected}
                with self.subTest(lemma=fixture['input']['lemma'], code=code):
                    self.assertEqual(values, wanted)
        setattr(VerbReferenceTests, f'test_original_{n:03}', test)


register()


def source(lemma='чита́ть', symbol='нсв', grammar='1a'):
    return {'lemma': lemma, 'symbol': symbol, 'grammar': grammar}


def forms(src, **selector):
    result = generate(src)[0]['generation']
    if result['status'] != 'generated': raise AssertionError(result)
    return [f for r in result['readings'] for f in r['forms']
            if all(f['features'].get(k) == v for k, v in selector.items())]


def words(src, **selector):
    return [f['stressed'] for f in forms(src, **selector)]


class ConjugationTests(unittest.TestCase):
    def test_present_six_personal_forms(self):
        self.assertEqual(words(source(), form='finite', tense='present'),
            ['чита́ю', 'чита́ешь', 'чита́ет', 'чита́ем', 'чита́ете', 'чита́ют'])

    def test_past_gender_and_plural(self):
        self.assertEqual(words(source(), form='finite', tense='past'),
                         ['чита́л', 'чита́ла', 'чита́ло', 'чита́ли'])

    def test_imperative(self):
        self.assertEqual(words(source(), form='imperative'), ['чита́й', 'чита́йте'])

    def test_future_perfective_and_absent_present(self):
        src = source('прочита́ть', 'св', '1a')
        self.assertEqual(words(src, form='finite', tense='future'),
                         ['прочита́ю', 'прочита́ешь', 'прочита́ет', 'прочита́ем', 'прочита́ете', 'прочита́ют'])
        self.assertTrue(all(f['status'] == 'absent' and f['word'] is None
                            for f in forms(src, form='finite', tense='present')))

    def test_biaspectual_preserves_both_tenses(self):
        src = source('организова́ть', 'св-нсв', '2a')
        for tense in ('present', 'future'):
            self.assertEqual(words(src, form='finite', tense=tense, person=1, number='singular'), ['организу́ю'])

    def test_consonant_alternation_and_mobile_stress(self):
        src = source('люби́ть', 'нсв', '4c')
        self.assertEqual(words(src, form='finite', tense='present'),
                         ['люблю́', 'лю́бишь', 'лю́бит', 'лю́бим', 'лю́бите', 'лю́бят'])

    def test_reflexive_postfix_depends_on_final_letter(self):
        src = source('мы́ться', 'нсв', '12a')
        self.assertEqual(words(src, form='finite', tense='present', person=1, number='singular'), ['мо́юсь'])
        self.assertEqual(words(src, form='finite', tense='past'), ['мы́лся', 'мы́лась', 'мы́лось', 'мы́лись'])
        self.assertEqual(words(src, form='imperative'), ['мо́йся', 'мо́йтесь'])

    def test_e_yo_and_type_eight_explicit_consonant(self):
        src = source('печь', 'нсв', '8b/b (-к-), ё')
        self.assertEqual(words(src, form='finite', tense='present'),
                         ['пеку́', 'печёшь', 'печёт', 'печём', 'печёте', 'пеку́т'])
        self.assertEqual(words(src, form='finite', tense='past'), ['пёк', 'пекла́', 'пекло́', 'пекли́'])

    def test_past_mobile_stress(self):
        src = source('взя́ть', 'св', '14b/c (-м-)')
        self.assertEqual(words(src, form='finite', tense='past'), ['взя́л', 'взяла́', 'взя́ло', 'взя́ли'])

    def test_prefix_fleeting_vowel(self):
        src = source('сби́ть', 'св', '11*b')
        self.assertEqual(words(src, form='finite', tense='future', person=1, number='singular'), ['собью́'])

    def test_passive_participle_declension_and_short_forms(self):
        src = source('реши́ть', 'св', '4b')
        self.assertEqual(words(src, form='participle', voice='passive', tense='past',
                              case='genitive', gender='feminine', number='singular'), ['решённой'])
        short = [f for f in forms(src, form='participle', voice='passive', tense='past') if 'case' not in f['features']]
        self.assertEqual([f['stressed'] for f in short], ['решён', 'решена́', 'решено́', 'решены́'])

    def test_active_participle_has_full_but_no_short_forms(self):
        fs = forms(source(), form='participle', voice='active', tense='present')
        self.assertIn('чита́ющего', [f['stressed'] for f in fs])
        self.assertTrue(all(f['status'] == 'absent' for f in fs if 'case' not in f['features']))

    def test_intransitive_and_reflexive_have_no_passive_participles(self):
        for src in (source('гуля́ть', 'нсв', 'нп 1a'), source('мы́ться', 'нсв', '12a')):
            self.assertTrue(all(f['status'] == 'absent' for f in forms(src, form='participle', voice='passive')))

    def test_gerund_variants(self):
        self.assertEqual(words(source(), form='gerund', tense='present'), ['чита́я'])
        self.assertEqual(set(words(source(), form='gerund', tense='past')), {'чита́в', 'чита́вши'})

    def test_optional_deviation_uses_independent_participle_stems(self):
        src = source('передразни́ть', 'св', '4c[⑦]')
        self.assertEqual(set(words(src, form='participle', voice='passive', tense='past',
            case='nominative', number='singular', gender='masculine')), {'передра́зненный', 'передразнённый'})

    def test_optional_imperative_deviation(self):
        src = source('вы́красить', 'св', '4a[③]')
        self.assertEqual(set(words(src, form='imperative', number='singular')), {'вы́краси', 'вы́крась'})
        self.assertEqual(words(src, form='imperative', number='plural'), ['вы́красьте'])

    def test_impersonal_only_has_third_singular_and_neuter_past(self):
        src = source('света́ть', 'нсв', 'нп 1a, безл.')
        fs = [f for f in forms(src) if f['status'] != 'absent']
        self.assertEqual([f['stressed'] for f in fs], ['света́ть', 'света́ло', 'света́ет'])

    def test_participle_restrictions(self):
        for marker, status in (('✕', 'difficult'), ('⌧', 'absent')):
            fs = forms(source('реши́ть', 'св', '4b' + marker), form='participle', tense='past', voice='passive')
            self.assertTrue(all(f['status'] == status for f in fs))

    def test_case_is_preserved(self):
        for lemma, wanted in (('Чита́ть', 'Чита́ю'), ('ЧИТА́ТЬ', 'ЧИТА́Ю')):
            self.assertEqual(words(source(lemma), form='finite', tense='present', person=1, number='singular'), [wanted])
        self.assertEqual(words(source('МЫ́ТЬСЯ', 'нсв', '12a'), form='imperative'), ['МО́ЙСЯ', 'МО́ЙТЕСЬ'])

    def test_secondary_stress_preserved_in_unchanged_prefix(self):
        fs = forms(source('сто̀литрова́ть'), form='finite', tense='present', person=1, number='singular')
        self.assertEqual(fs[0]['word']['accent_variants'][0]['secondary'], [3])
        self.assertEqual(fs[0]['stressed'], 'сто̀литрова́ю')

    def test_no_silent_guess_for_missing_alternation_or_bad_suffix(self):
        for src in (source('печь', 'нсв', '8b'), source('взя́ть', 'св', '14b'),
                    source('чита́ть', 'нсв', '4a'), source('ить', 'нсв', '4b'), source('чита́ть', 'нсв', '1f')):
            result = generate(src)[0]['generation']
            self.assertEqual(result['status'], 'blocked', src)
            self.assertEqual(result['readings'][0]['forms'], [])
            self.assertEqual(result['readings'][0]['diagnostics'][0]['code'], 'CONJUGATION_UNSUPPORTED')

    def test_model_and_source_not_mutated(self):
        src = source('реши́ть', 'св', '4b')
        normalized = analyze(src)
        saved = copy.deepcopy(normalized)
        self.assertEqual(generate_analyzed(normalized), generate(src))
        self.assertEqual(saved, normalized)

    def test_partner_is_metadata_and_does_not_create_new_lemma(self):
        src = source('столкну́ть', 'св', '3b ◑I(-а́-)')
        result = generate(src)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['readings'][0]['verb']['partner']['type'], 'I')
        self.assertEqual(result[0]['generation']['status'], 'generated')


if __name__ == '__main__':
    unittest.main()
