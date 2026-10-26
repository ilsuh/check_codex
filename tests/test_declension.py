"""Независимые языковые примеры и парадигмы исходного Perl-генератора."""
from collections import Counter
import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from zaliz import analyze, generate, generate_analyzed

ROOT = Path(__file__).resolve().parents[1]
CASES = dict(zip('ирдвтп', ['nominative', 'genitive', 'dative', 'accusative', 'instrumental', 'prepositional']))
GENDERS = {'м': 'masculine', 'ж': 'feminine', 'с': 'neuter'}


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def article(lemma='столбе́ц', symbol='м', grammar='5*b'):
    return {'lemma': lemma, 'symbol': symbol, 'grammar': grammar}


def forms(source, **selector):
    result = generate(source)[0]['generation']
    if result['status'] != 'generated':
        raise AssertionError(result)
    return [f for reading in result['readings'] for f in reading['forms']
            if all(f['features'].get(k) == v for k, v in selector.items())]


def stressed(source, **selector):
    return [f['stressed'] for f in forms(source, **selector)]


def code_selector(code, pos):
    # Независимое сопоставление обозначений оригинала именованным признакам.
    if pos == 'с':
        return {'case': CASES[code[0]], 'number': 'singular' if code[1] == 'е' else 'plural'}
    if code == 'с':
        return {'form': 'comparative'}
    prefix, case, number, *rest = code
    result = {'form': 'full' if prefix == 'п' else 'short',
              'number': 'singular' if number == 'е' else 'plural'}
    if prefix == 'п': result['case'] = CASES[case]
    if number == 'е': result['gender'] = GENDERS[rest.pop(0)]
    elif prefix == 'к': rest = []
    if rest: result['animacy'] = 'animate' if rest[-1] == 'о' else 'inanimate'
    return result


class ReferenceTests(unittest.TestCase):
    fixtures = load('tests/fixtures/declension.reference.json')['cases']

    def test_reference_coverage(self):
        self.assertEqual(len(self.fixtures), 318)
        self.assertEqual(sum(len(c['expected']) for c in self.fixtures), 7059)
        self.assertEqual({c['adb']['и'] for c in self.fixtures if c['adb']['т'] == 'с'}, set('12345678'))
        self.assertTrue({'b1', 'd1', 'e', 'f1', 'f2'}.issubset({c['adb']['у1'] for c in self.fixtures}))
        self.assertTrue({'b', 'c', 'b1', 'c1', 'c2'}.issubset({c['adb'].get('у2') for c in self.fixtures}))


def register_reference_tests():
    for index, fixture in enumerate(ReferenceTests.fixtures):
        def test(self, fixture=fixture):
            result = generate(fixture['input'])[0]['generation']
            self.assertEqual(result['status'], 'generated', result)
            actual_forms = result['readings'][0]['forms']
            for code, expected in fixture['expected'].items():
                selector = code_selector(code, fixture['adb']['т'])
                actual = [f for f in actual_forms if all(f['features'].get(k) == v for k, v in selector.items())]
                values = {(f['word']['text'] if f['word'] else None,
                           (f['word']['accent_variants'][0]['primary'] or [0])[0] if f['word'] else None,
                           f['status']) for f in actual}
                wanted = {(f['text'], f['primary'], f['status']) for f in expected}
                with self.subTest(article=fixture['input'], code=code):
                    self.assertEqual(values, wanted)
        setattr(ReferenceTests, f'test_original_{index:03d}', test)


register_reference_tests()


class DeclensionTests(unittest.TestCase):
    def test_stolbets_all_twelve_forms(self):
        actual = stressed(article())
        self.assertEqual(actual, ['столбе́ц', 'столбца́', 'столбцу́', 'столбе́ц', 'столбцо́м', 'столбце́',
                                  'столбцы́', 'столбцо́в', 'столбца́м', 'столбцы́', 'столбца́ми', 'столбца́х'])

    def test_animate_accusative(self):
        self.assertEqual(stressed(article('оте́ц', 'мо', '5*b'), case='accusative', number='singular'), ['отца́'])
        self.assertEqual(stressed(article('врач', 'мо', '4b'), case='accusative', number='plural'), ['враче́й'])

    def test_masculine_with_feminine_declension(self):
        source = article('столяри́шка', 'мо', '<жо 3*a>')
        self.assertEqual(stressed(source, case='accusative', number='singular'), ['столяри́шку'])
        self.assertEqual(stressed(source, case='genitive', number='plural'), ['столяри́шек'])

    def test_neuter_declension_preserves_lexical_gender(self):
        source = article('столи́ще', 'м', '<с 4a[①]>')
        self.assertEqual(set(stressed(source, case='nominative', number='plural')), {'столи́ща', 'столи́щи'})
        self.assertTrue(all(f['features']['gender'] == 'masculine' for f in forms(source)))

    def test_plural_only_has_no_singular(self):
        result = forms(article('столбцы́', 'мн.', '<м 5*b>'))
        self.assertEqual(len(result), 6)
        self.assertTrue(all(f['features']['number'] == 'plural' for f in result))
        self.assertEqual([f['stressed'] for f in result], ['столбцы́', 'столбцо́в', 'столбца́м', 'столбцы́', 'столбца́ми', 'столбца́х'])

    def test_indeclinable_noun(self):
        result = forms(article('ко́фе', 'м', '0'))
        self.assertEqual(len(result), 12)
        self.assertEqual({f['stressed'] for f in result}, {'ко́фе'})

    def test_female_instrumental_variants(self):
        self.assertEqual(stressed(article('кни́га', 'ж', '3a'), case='instrumental', number='singular'), ['кни́гой', 'кни́гою'])

    def test_uppercase_and_initial_capital_survive_stem_changes(self):
        self.assertEqual(stressed(article('Лев', 'мо', '1*b'), case='genitive', number='singular'), ['Льва́'])
        self.assertEqual(stressed(article('ЛЕВ', 'мо', '1*b'), case='genitive', number='singular'), ['ЛЬВА́'])
        self.assertEqual(stressed(article('СТОЛБЕ́Ц', 'м', '5*b'), case='genitive', number='singular'), ['СТОЛБЦА́'])

    def test_mobile_stress_and_fleeting_vowel(self):
        source = article('окно́', 'с', '1*d')
        self.assertEqual(stressed(source, case='genitive', number='singular'), ['окна́'])
        self.assertEqual(stressed(source, case='genitive', number='plural'), ['о́кон'])

    def test_female_soft_stem_instrumental(self):
        self.assertEqual(stressed(article('ночь', 'ж', '8e'), case='instrumental', number='singular'), ['но́чью'])

    def test_stress_exception_b_prime(self):
        self.assertEqual(stressed(article('любо́вь', 'ж', "8*b'"), case='instrumental', number='singular'), ['любо́вью'])

    def test_special_stem_child(self):
        source = article('котёнок', 'мо', '3°a')
        self.assertEqual(stressed(source, case='genitive', number='singular'), ['котёнка'])
        self.assertEqual(stressed(source, case='nominative', number='plural'), ['котя́та'])

    def test_special_stem_in(self):
        source = article('крестья́нин', 'мо', '1°a')
        self.assertEqual(stressed(source, case='nominative', number='plural'), ['крестья́не'])

    def test_special_neuter_and_yo_alternation(self):
        source = article('и́мя', 'с', '8°c, ё')
        self.assertEqual(stressed(source, case='genitive', number='singular'), ['и́мени'])
        self.assertEqual(stressed(source, case='genitive', number='plural'), ['имён'])

    def test_short_forms_and_yo(self):
        source = article('жёлтый', 'п', '1a/b, ё')
        self.assertEqual(stressed(source, form='short', number='singular', gender='feminine'), ['желта́'])
        self.assertEqual(stressed(source, form='comparative'), ['желте́е', 'желте́й'])

    def test_regular_comparative(self):
        self.assertEqual(stressed(article('краси́вый', 'п', '1a'), form='comparative'), ['краси́вее', 'краси́вей'])
        self.assertEqual(stressed(article('ти́хий', 'п', '3a'), form='comparative'), ['ти́ше'])

    def test_short_fleeting_vowel(self):
        self.assertEqual(stressed(article('кра́ткий', 'п', '3*a'), form='short', number='singular', gender='masculine'), ['кра́ток'])

    def test_adjective_neuter_accusative_is_nominative(self):
        source = article('краси́вый', 'п', '1a')
        for animacy in ('inanimate', 'animate'):
            self.assertEqual(stressed(source, form='full', case='accusative', number='singular', gender='neuter', animacy=animacy), ['краси́вое'])

    def test_noun_of_adjectival_declension(self):
        source = article('столо́вая', 'ж', '<п 1a>')
        self.assertEqual(stressed(source, case='accusative', number='singular'), ['столо́вую'])
        self.assertFalse(any('form' in f['features'] for f in forms(source)))

    def test_pronominal_declension(self):
        source = article('ли́сий', 'п', '<мс 6*a>')
        self.assertEqual(stressed(source, form='full', case='nominative', number='singular', gender='feminine'), ['ли́сья'])
        self.assertEqual(stressed(source, form='full', case='genitive', number='singular', gender='masculine'), ['ли́сьего'])
        self.assertTrue(all(f['status'] == 'absent' for f in forms(source, form='short')))

    def test_surname_both_genders_and_possessive_special_endings(self):
        source = article('Столе́тов', 'ф.', '<мс 1a>')
        self.assertEqual(stressed(source, case='genitive', number='singular', gender='masculine'), ['Столе́това'])
        self.assertEqual(stressed(source, case='instrumental', number='singular', gender='masculine'), ['Столе́товым'])
        self.assertEqual(stressed(source, case='nominative', number='singular', gender='feminine'), ['Столе́това'])
        self.assertEqual(stressed(source, case='genitive', number='plural'), ['Столе́товых'])
        self.assertEqual(stressed(article('ма́мин', 'п', '<мс 1a>'), form='full', case='genitive', number='singular', gender='masculine'), ['ма́мина'])

    def test_absent_and_difficult_are_distinct(self):
        source = article('столбово́й', 'п', '1b⌧')
        male = forms(source, form='short', number='singular', gender='masculine')
        female = forms(source, form='short', number='singular', gender='feminine')
        self.assertEqual(male[0]['status'], 'absent')
        self.assertIsNone(male[0]['word'])
        self.assertEqual(female[0]['status'], 'difficult')
        self.assertIsNotNone(female[0]['word'])
        self.assertTrue(all(f['status'] == 'absent' for f in forms(article('столи́кий','п','3a~'), form='comparative')))

    def test_alternative_stresses_and_secondary_stress(self):
        source = article('сто́лбча́тый', 'п', '1a')
        actual = stressed(source, case='genitive', number='singular', gender='masculine')
        self.assertEqual(actual, ['сто́лбчатого', 'столбча́того'])
        source = article('сто̀литро́вый', 'п', '1a')
        self.assertEqual(stressed(source, case='genitive', number='singular', gender='masculine'), ['сто̀литро́вого'])

    def test_explicit_numeral_relations_and_separate_pronoun(self):
        generated = generate(load('examples/group.json'))
        numeral = generated[61]['generation']['readings'][1]['forms']
        self.assertEqual({f['stressed'] for f in numeral if f['features'] == {'case':'accusative','animacy':'animate'}}, {'сто́льких', 'сто́лько'})
        pronoun = generated[62]['generation']['readings'][0]['forms']
        self.assertEqual([f['stressed'] for f in pronoun if f['features']['case']=='genitive'], ['сто́лького'])
        little = generated[19]['generation']['readings'][1]['forms']
        self.assertTrue(all(f['status']=='absent' for f in little if f['features']['case'] in ('genitive','dative','instrumental','prepositional')))

    def test_new_parse_features_against_independent_expectations(self):
        validator = Draft202012Validator(load('schemas/analysis.schema.json'))
        for fixture in load('tests/fixtures/declension-parse.expected.json'):
            with self.subTest(source=fixture['input']):
                actual = analyze(fixture['input'])[0]
                self.assertEqual(actual, fixture['expected'])
                validator.validate(actual)

    def test_user_group_and_schema(self):
        output = generate(load('examples/group.json'))
        schema = load('schemas/generation.schema.json')
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual(Counter(x['generation']['status'] for x in output), {'generated':75,'blocked':2})
        for i, item in enumerate(output):
            with self.subTest(index=i):
                validator.validate(item['generation'])
        self.assertEqual([{k:v for k,v in item.items() if k!='generation'} for item in output], analyze(load('examples/group.json')))

    def test_no_mutation_and_repeatability(self):
        payload = load('examples/group.json')
        original = copy.deepcopy(payload)
        normalized = analyze(payload)
        normalized_original = copy.deepcopy(normalized)
        self.assertEqual(generate(payload), generate_analyzed(normalized))
        self.assertEqual(payload, original)
        self.assertEqual(normalized, normalized_original)

    def test_unsupported_does_not_issue_partial_paradigm(self):
        source = article('ба́ба-яга́', 'жо', '1a')
        g = generate(source)[0]['generation']
        self.assertEqual(g['status'], 'blocked')
        self.assertEqual(g['readings'][0]['forms'], [])
        self.assertTrue(g['readings'][0]['diagnostics'])

    def test_secondary_stress_on_a_removed_vowel_is_not_silently_lost(self):
        result = generate(article('за́мо̀к', 'м', '3*a'))[0]['generation']
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['readings'][0]['forms'], [])
        self.assertIn('побочного ударения', result['readings'][0]['diagnostics'][0]['message'])

    def test_unknown_and_unresolved_grammar_block_generation(self):
        for source in (article(grammar='5*b § неизвестно'),article('столо́чь','св','спряж. см. затоло́чь')):
            with self.subTest(source=source):
                g=generate(source)[0]['generation']
                self.assertEqual(g['status'],'blocked')
                self.assertEqual(g['readings'],[])

    def test_verb_does_not_disguise_itself_as_declension(self):
        g=generate(article('рисова́ть','нсв','2a'))[0]['generation']
        self.assertEqual(g['status'],'generated')
        self.assertTrue(all('case' not in f['features'] for f in g['readings'][0]['forms']
                            if f['features']['form'] != 'participle'))

    def test_missing_or_inapplicable_stress_is_not_replaced_with_a_guess(self):
        for source in (article('но́вый', 'п', '1c'), article('стол', 'м', "1a'")):
            with self.subTest(source=source):
                self.assertEqual(generate(source)[0]['generation']['status'], 'blocked')
        normalized = analyze(article())
        normalized[0]['readings'][0]['inflection']['stress']['full'] = None
        result = generate_analyzed(normalized)[0]['generation']
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['readings'][0]['forms'], [])

    def test_cyclic_explicit_relations_do_not_loop_or_issue_partial_forms(self):
        source = article('что', 'мс', 'Р.=Д., Д.=Р., Т. чем, П. чём, В.=И.')
        result = generate(source)[0]
        self.assertEqual(result['status'], 'parsed')
        self.assertEqual(result['generation']['status'], 'blocked')
        self.assertEqual(result['generation']['readings'][0]['forms'], [])

    def test_every_generated_accent_is_on_a_vowel(self):
        for article_result in generate(load('examples/group.json')):
            for reading in article_result['generation']['readings']:
                for form in reading['forms']:
                    if form['word']:
                        word=form['word']
                        for accent in word['accent_variants']:
                            for position in accent['primary']+accent['secondary']:
                                self.assertIn(word['text'][position-1].lower(),'аеёиоуыэюя')


if __name__ == '__main__':
    unittest.main()
