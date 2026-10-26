"""Проверки настоящего парсера: независимые эталоны и новые описания."""
import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from zaliz import InputError, analyze

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def article(lemma='сто́лик', symbol='м', grammar='3a'):
    return {'lemma': lemma, 'symbol': symbol, 'grammar': grammar}


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = analyze(load('examples/group.json'))
        cls.expected = load('tests/fixtures/group.expected.json')
        cls.validator = Draft202012Validator(load('schemas/analysis.schema.json'))

    def test_single(self):
        self.assertEqual(analyze(load('examples/single.json')), load('tests/fixtures/single.expected.json'))

    def test_error_expectations(self):
        for case in load('tests/fixtures/errors.expected.json'):
            with self.subTest(case=case['name']):
                actual = analyze(case['input'])[0]
                self.validator.validate(actual)
                self.assertEqual(actual, case['expected'])


def register_fixture_tests():
    for index in range(77):
        def test(self, index=index):
            actual = self.actual[index]
            self.validator.validate(actual)
            self.assertEqual(actual, self.expected[index])
        setattr(FixtureTests, f'test_group_{index:02d}', test)


register_fixture_tests()


class ParserTests(unittest.TestCase):
    def test_empty_group(self):
        self.assertEqual(analyze([]), [])

    def test_rejects_document_structure(self):
        for payload in ('{}', None, 42, [42], {'entries': []}, [article(), []]):
            with self.subTest(payload=payload), self.assertRaises(InputError):
                analyze(payload)

    def test_bad_article_does_not_stop_group(self):
        results = analyze([article(), {'lemma': 'друго́й', 'symbol': 'п', 'grammar': 1}, article('книга́', 'ж', '3b')])
        self.assertEqual([r['status'] for r in results], ['parsed', 'invalid', 'parsed'])
        self.assertEqual([r['source_index'] for r in results], [0, 1, 2])

    def test_empty_symbol_is_invalid(self):
        for symbol in ('', '   ', '<i></i>'):
            with self.subTest(symbol=symbol):
                self.assertEqual(analyze(article(symbol=symbol))[0]['status'], 'invalid')

    def test_inherits_only_last_explicit_lemma(self):
        source = [article('стол', 'м', '1b'), article('', 'мо', '1b'), article('  ', 'м', '1a')]
        results = analyze(source)
        self.assertEqual([r['effective_lemma'] for r in results], ['стол'] * 3)
        self.assertEqual([r['inherited_from'] for r in results], [None, 0, 0])
        self.assertEqual(results[1]['readings'][0]['animacy'], 'animate')
        self.assertEqual(results[2]['readings'][0]['inflection']['stress']['full'], 'a')

    def test_bad_grammar_does_not_erase_explicit_headword(self):
        results = analyze([article('пла́н', 'м', '☃'), article('', 'м', '1a')])
        self.assertEqual(results[0]['status'], 'unsupported')
        self.assertEqual(results[1]['status'], 'parsed')
        self.assertEqual(results[1]['headword']['text'], 'план')
        self.assertEqual(results[1]['inherited_from'], 0)

    def test_lexeme_context_survives_wrong_field_type(self):
        results = analyze([article('пла́н', 'м', 1), article('', 'м', '1a')])
        self.assertEqual(results[0]['status'], 'invalid')
        self.assertEqual(results[1]['headword']['text'], 'план')

    def test_no_context_between_calls(self):
        analyze(article('пла́н', 'м', '1a'))
        self.assertEqual(analyze(article('', 'м', '1a'))[0]['status'], 'invalid')

    def test_preserves_source_and_does_not_alias_nested_data(self):
        source = [article()]
        source[0]['extra'] = {'comments': ['помета']}
        original = copy.deepcopy(source)
        results = analyze(source)
        self.assertEqual(source, original)
        results[0]['source']['extra']['comments'].append('изменение результата')
        self.assertEqual(source, original)

    def test_repeatability(self):
        source = article('рисова́ть', 'нсв', '2a')
        self.assertEqual(analyze(source), analyze(source))

    def test_equivalent_html_entities_and_literal_angles(self):
        first = analyze(article('ма́стерская', 'ж', '<п 1a>'))[0]
        second = analyze(article('ма́стерская', 'ж', '&lt;п 1a&gt;'))[0]
        self.assertEqual(first['readings'], second['readings'])
        self.assertEqual(first['readings'][0]['inflection']['family'], 'adjectival')

    def test_pronominal_pattern_is_not_an_html_tag(self):
        result = analyze(article('ли́сий', 'п', '<мс 6*a>'))[0]
        self.assertEqual(result['status'], 'parsed')
        self.assertEqual(result['readings'][0]['inflection']['family'], 'pronominal')
        self.assertTrue(result['readings'][0]['inflection']['fleeting_vowel'])

    def test_russian_stress_letter(self):
        result = analyze(article(grammar='3а'))[0]
        self.assertEqual(result['status'], 'parsed')
        self.assertEqual(result['readings'][0]['inflection']['stress']['full'], 'a')

    def test_short_and_past_stress_are_distinct(self):
        adj = analyze(article('но́вый', 'п', "1a/c'"))[0]['readings'][0]
        verb = analyze(article('нести́', 'нсв', '7b/b (-с-)'))[0]['readings'][0]
        self.assertEqual(adj['inflection']['stress'], {'full': 'a', 'short': "c'", 'past': None})
        self.assertEqual(verb['inflection']['stress'], {'full': 'b', 'short': None, 'past': 'b'})
        self.assertEqual(verb['inflection']['consonant_alternation'], 'с')

    def test_partner_is_not_current_consonant_alternation(self):
        result = analyze(article('толкну́ть', 'св', '3b ◑I(-а́-)'))[0]
        self.assertEqual(result['status'], 'parsed')
        r = result['readings'][0]
        self.assertIsNone(r['inflection']['consonant_alternation'])
        self.assertEqual(r['verb']['partner']['replacement'], '-а́-')

    def test_unknown_morphology_remains_visible(self):
        for grammar in ('3a ☃', '3a § неизвестно', '3a △ неизвестно', '3a // 3b'):
            with self.subTest(grammar=grammar):
                result = analyze(article(grammar=grammar))[0]
                self.assertEqual(result['status'], 'unsupported')
                self.assertTrue(result['unparsed'])
                self.assertEqual(result['source']['grammar'], grammar)

    def test_invalid_index(self):
        for source in (article(grammar='9a'), article('гуля́ть', 'нсв', '0')):
            with self.subTest(source=source):
                self.assertEqual(analyze(source)[0]['status'], 'invalid')

    def test_case_instruction_is_not_a_meaning(self):
        result = analyze(article(grammar='3a (<i>Р. мн.</i> бра́тьев)'))[0]
        self.assertEqual(result['status'], 'unsupported')
        self.assertEqual(result['annotations'], [])

    def test_unimplemented_restriction_is_not_a_gloss(self):
        for instruction in ('только мн.', 'употр. только кф', 'форм нет', 'не имеет мн.'):
            with self.subTest(instruction=instruction):
                result = analyze(article(grammar=f'3a (<i>{instruction}</i>)'))[0]
                self.assertEqual(result['status'], 'unsupported')
                self.assertIn(instruction, result['unparsed'][0])

    def test_np_prefix_and_suffix(self):
        first = analyze(article('гуля́ть', 'нсв', 'нп 1a'))[0]
        second = analyze(article('гуля́ть', 'нсв', '1a нп'))[0]
        self.assertEqual(first['readings'], second['readings'])
        self.assertEqual(first['readings'][0]['verb']['transitivity_basis'], 'explicit_marker')

    def test_np_is_not_silently_removed_from_a_noun(self):
        self.assertEqual(analyze(article(grammar='нп 3a'))[0]['status'], 'unsupported')

    def test_reflexivity_and_transitivity_basis(self):
        r = analyze(article('гуля́ться', 'нсв', '1a'))[0]['readings'][0]
        self.assertTrue(r['verb']['reflexive'])
        self.assertEqual(r['verb']['transitivity'], 'intransitive')
        self.assertEqual(r['verb']['transitivity_basis'], 'reflexive')

    def test_unicode_nfc(self):
        first = analyze(article('геро́й', 'мо', '6a'))[0]
        second = analyze(article('геро́й', 'мо', '6a'))[0]
        self.assertEqual(first['headword'], second['headword'])
        result = analyze(article('всё', 'мс', 'И. всё, Р. всего́, Д. всему́, В.=И., Т. всем, П. всём'))[0]
        self.assertEqual(result['headword']['text'], 'всё')
        self.assertEqual(result['headword']['accent_variants'][0]['basis'], 'yo')

    def test_alternative_accents_without_hyphen(self):
        result = analyze(article('и́скри́стый', 'п', '1a'))[0]
        self.assertEqual([v['primary'] for v in result['headword']['accent_variants']], [[1], [5]])

    def test_simultaneous_accents_with_hyphen(self):
        result = analyze(article('ба́ба-яга́', 'жо', '1a'))[0]
        self.assertEqual(result['headword']['accent_variants'][0]['primary'], [2, 8])

    def test_invalid_accent_is_not_ignored(self):
        for lemma in ('с́тол', 'сто́̀л', 'сто́́л'):
            with self.subTest(lemma=lemma):
                self.assertEqual(analyze(article(lemma, 'м', '1b'))[0]['status'], 'invalid')

    def test_unstressed_word_overrides_monosyllable_default(self):
        for grammar in ('(<i>без удар.</i>)', '(без удар.)'):
            with self.subTest(grammar=grammar):
                result = analyze(article('ведь', 'н', grammar))[0]
                self.assertEqual(result['status'], 'parsed')
                self.assertEqual(result['headword']['accent_variants'],
                                 [{'primary': [], 'secondary': [], 'basis': 'unstressed'}])

    def test_unsupported_stress_condition_does_not_disappear(self):
        result = analyze(article('от', 'н', '(<i>нормально без удар.</i>)'))[0]
        self.assertEqual(result['status'], 'unsupported')
        self.assertTrue(result['unparsed'])

    def test_explicit_forms_are_not_tied_to_fixture_word(self):
        result = analyze(article('не́что', 'мс', 'Р. не́ч|его, Д. -ему, Т. -ем, П. -ем, В.=И.'))[0]
        self.assertEqual(result['status'], 'parsed')
        self.assertEqual([f['word']['text'] for f in result['readings'][0]['explicit_forms']],
                         ['нечто', 'нечего', 'нечему', 'нечем', 'нечем'])

    def test_incomplete_explicit_forms(self):
        for grammar in ('Р. не́ч|его, В.=И.', 'Р. -его, Д. -ему, Т. -ем, П. -ем, В.=И.'):
            with self.subTest(grammar=grammar):
                self.assertEqual(analyze(article('не́что', 'мс', grammar))[0]['status'], 'unsupported')


class ReferenceTests(unittest.TestCase):
    def test_forward_and_backward_references(self):
        alias = article('порисова́ть', 'св', 'спряж. см. рисова́ть')
        target = article('рисова́ть', 'нсв', '2a')
        for source, alias_index, target_index in (([alias, target], 0, 1), ([target, alias], 1, 0)):
            with self.subTest(alias_index=alias_index):
                result = analyze(source)
                self.assertTrue(all(r['status'] == 'parsed' for r in result))
                ref = result[alias_index]['readings'][0]['reference']
                self.assertEqual(ref['resolution'], 'resolved')
                self.assertEqual(ref['source_index'], target_index)
                self.assertIsNone(result[alias_index]['readings'][0]['inflection']['index'])

    def test_wrong_part_of_speech_is_not_a_conjugation_target(self):
        result = analyze([article('порисова́ть', 'св', 'спряж. см. рисова́ть'), article('рисова́ть', 'м', '1a')])
        self.assertEqual(result[0]['diagnostics'][0]['code'], 'MISSING_REFERENCE')

    def test_target_accent_is_not_part_of_lookup_key(self):
        result = analyze([article('порисова́ть', 'св', 'спряж. см. рисовать'), article('рисова́ть', 'нсв', '2a')])
        self.assertEqual(result[0]['status'], 'parsed')

    def test_ambiguous_reference(self):
        result = analyze([article('порисова́ть', 'св', 'спряж. см. рисова́ть'),
                          article('рисова́ть', 'нсв', '2a'), article('рисова́ть', 'нсв', '1a')])
        self.assertEqual(result[0]['diagnostics'][0]['code'], 'AMBIGUOUS_REFERENCE')
        self.assertIsNone(result[0]['readings'][0]['reference']['source_index'])

    def test_failed_target_does_not_resolve_reference(self):
        result = analyze([article('порисова́ть', 'св', 'спряж. см. рисова́ть'),
                          article('рисова́ть', 'нсв', '2a ☃')])
        self.assertEqual(result[0]['status'], 'needs_reference')
        self.assertEqual(result[1]['status'], 'unsupported')

    def test_missing_dependency_propagates(self):
        result = analyze([article('а́кать', 'нсв', 'спряж. см. ба́кать'),
                          article('ба́кать', 'нсв', 'спряж. см. ва́кать')])
        self.assertEqual([r['status'] for r in result], ['needs_reference', 'needs_reference'])
        self.assertEqual(result[0]['readings'][0]['reference']['source_index'], 1)
        self.assertEqual(result[0]['diagnostics'][0]['code'], 'MISSING_REFERENCE')

    def test_self_reference_cycle(self):
        result = analyze(article('а́кать', 'нсв', 'спряж. см. а́кать'))[0]
        self.assertEqual(result['diagnostics'][0]['code'], 'REFERENCE_CYCLE')

    def test_cycles_and_dependent_aliases(self):
        result = analyze([article('а́кать', 'нсв', 'спряж. см. ба́кать'),
                          article('ба́кать', 'нсв', 'спряж. см. ва́кать'),
                          article('ва́кать', 'нсв', 'спряж. см. ба́кать')])
        self.assertEqual([r['diagnostics'][0]['code'] for r in result], ['REFERENCE_CYCLE'] * 3)

    def test_long_reference_chain_does_not_use_python_recursion(self):
        consonants = 'бвгджзклмнпрстфхцчшщ'
        def name(i):
            letters = ''
            while True:
                letters = consonants[i % len(consonants)] + letters
                i //= len(consonants)
                if not i:
                    return 'а́' + letters + 'ать'
        count = 1200
        sources = [article(name(i), 'нсв', 'спряж. см. ' + name(i + 1)) for i in range(count - 1)]
        sources.append(article(name(count - 1), 'нсв', '1a'))
        result = analyze(sources)
        self.assertEqual(len(result), count)
        self.assertTrue(all(r['status'] == 'parsed' for r in result))


if __name__ == '__main__':
    unittest.main()
