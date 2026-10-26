"""Проверяем схемы и целостность эталонов. Парсер здесь НЕ вызывается.

Сами по себе эти проверки не подтверждают работу парсера или генератора.
Настоящий парсер отдельно проверяется в test_parser.py; генератора ещё нет.
"""
import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_schema = load('schemas/input.schema.json')
        cls.analysis_schema = load('schemas/analysis.schema.json')
        cls.input_validator = Draft202012Validator(cls.input_schema)
        cls.analysis_validator = Draft202012Validator(cls.analysis_schema)
        cls.group = load('examples/group.json')
        cls.expected = load('tests/fixtures/group.expected.json')

    def test_schemas_are_valid(self):
        Draft202012Validator.check_schema(self.input_schema)
        Draft202012Validator.check_schema(self.analysis_schema)

    def test_single_and_group_inputs(self):
        self.input_validator.validate(load('examples/single.json'))
        self.input_validator.validate(self.group)
        self.input_validator.validate([])

    def test_rejects_unrelated_envelopes_and_invalid_fields(self):
        for data in (None, 'стол', {'entries': self.group}, [42],
                     {'lemma': 'стол', 'symbol': 'м'},
                     {'lemma': 'стол', 'symbol': 'м', 'grammar': 5}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                self.input_validator.validate(data)

    def test_group_has_one_expected_result_per_article(self):
        self.assertEqual(len(self.group), 77)
        self.assertEqual(len(self.expected), len(self.group))
        for i, (source, expected) in enumerate(zip(self.group, self.expected)):
            with self.subTest(index=i):
                self.analysis_validator.validate(expected)
                self.assertEqual(expected['source_index'], i)
                self.assertEqual(expected['source'], source)

    def test_inheritance_points_to_last_explicit_headword(self):
        last_index = None
        for i, (source, expected) in enumerate(zip(self.group, self.expected)):
            with self.subTest(index=i):
                if source['lemma']:
                    last_index = i
                    self.assertIsNone(expected['inherited_from'])
                else:
                    self.assertEqual(expected['inherited_from'], last_index)
                self.assertEqual(expected['effective_lemma'], self.group[last_index]['lemma'])
        self.assertEqual([e['source_index'] for e in self.expected if e['inherited_from'] is not None], [1, 49, 62])

    def test_single_expectation_is_independent_of_group_index(self):
        expected = load('tests/fixtures/single.expected.json')
        self.assertEqual(len(expected), 1)
        self.analysis_validator.validate(expected[0])
        self.assertEqual(expected[0]['source_index'], 0)
        self.assertEqual(expected[0]['source'], load('examples/single.json'))

    def test_lexical_gender_and_declension_pattern_are_distinct(self):
        bigger_table = self.expected[28]['readings'][0]
        carpenter = self.expected[70]['readings'][0]
        self.assertEqual(bigger_table['gender'], 'masculine')
        self.assertEqual(bigger_table['inflection']['pattern_gender'], 'neuter')
        self.assertEqual(bigger_table['deviations'], [{'number': 1, 'optional': True}])
        self.assertEqual(carpenter['gender'], 'masculine')
        self.assertEqual(carpenter['inflection']['pattern_gender'], 'feminine')
        self.assertEqual(self.expected[36]['readings'][0]['inflection']['family'], 'adjectival')

    def test_multiple_parts_of_speech_remain_separate(self):
        for i in (19, 61):
            self.assertEqual([r['part_of_speech'] for r in self.expected[i]['readings']], ['adverb', 'numeral'])
        self.assertEqual(self.expected[62]['readings'][0]['part_of_speech'], 'pronoun')
        self.assertEqual(sum(len(e['readings']) for e in self.expected), 79)

    def test_explicit_forms_have_expanded_endings(self):
        numeral = self.expected[61]['readings'][1]
        pronoun = self.expected[62]['readings'][0]
        self.assertEqual([f['word']['text'] for f in numeral['explicit_forms']],
                         ['столько', 'стольких', 'стольким', 'столькими', 'стольких'])
        self.assertEqual([f['word']['text'] for f in pronoun['explicit_forms']],
                         ['столько', 'столького', 'столькому', 'стольким', 'стольком'])
        self.assertEqual(numeral['relations'][1]['same_as'],
                         [{'case': 'genitive'}, {'case': 'nominative'}])

    def test_primary_variants_and_secondary_stress_are_distinct(self):
        variants = self.expected[14]['headword']['accent_variants']
        self.assertEqual([v['primary'] for v in variants], [[3], [7]])
        compound = self.expected[25]['headword']['accent_variants']
        self.assertEqual(compound, [{'primary': [8], 'secondary': [3], 'basis': 'explicit'}])

    def test_accents_refer_to_vowels_in_normalized_words(self):
        words = []
        for entry in self.expected:
            words.append(entry['headword'])
            for reading in entry['readings']:
                words.extend(f['word'] for f in reading['explicit_forms'])
                if reading['reference']:
                    words.append(reading['reference']['target'])
        for word in words:
            for accent in word['accent_variants']:
                for pos in accent['primary'] + accent['secondary']:
                    with self.subTest(word=word['text'], position=pos):
                        self.assertTrue(0 < pos <= len(word['text']))
                        self.assertIn(word['text'][pos - 1].lower(), 'аеёиоуыэюя')

    def test_unresolved_references_are_not_regular_paradigms(self):
        pending = [e for e in self.expected if e['status'] == 'needs_reference']
        self.assertEqual([e['source_index'] for e in pending], [46, 47])
        self.assertEqual([e['readings'][0]['reference']['target']['text'] for e in pending],
                         ['затолочь', 'затолочься'])
        for entry in pending:
            self.assertIsNone(entry['readings'][0]['inflection']['index'])
            self.assertEqual(entry['diagnostics'][0]['code'], 'MISSING_REFERENCE')

    def test_error_expectations_fit_model_and_keep_input(self):
        for case in load('tests/fixtures/errors.expected.json'):
            with self.subTest(case=case['name']):
                self.analysis_validator.validate(case['expected'])
                self.assertEqual(case['expected']['source'], case['input'])
                self.assertIn(case['expected']['status'], ('invalid', 'unsupported'))

    def test_success_cannot_contain_an_unresolved_reference(self):
        bad = copy.deepcopy(self.expected[46])
        bad['status'] = 'parsed'
        bad['diagnostics'] = []
        with self.assertRaises(ValidationError):
            self.analysis_validator.validate(bad)

    def test_success_cannot_hide_unparsed_grammar(self):
        for field, value in [('unparsed', ['☃']),
                             ('diagnostics', [{'code': 'UNSUPPORTED_GRAMMAR', 'message': 'Неизвестный знак'}]),
                             ('readings', []), ('headword', None)]:
            bad = copy.deepcopy(self.expected[5])
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.analysis_validator.validate(bad)


if __name__ == '__main__':
    unittest.main()
