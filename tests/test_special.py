"""Исключения, дополнительные падежи, образцы и видовые связи."""
import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from zaliz import analyze, generate, generate_analyzed
from test_conjugation import verb_selector
from test_declension import code_selector

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / 'tests/fixtures/special.reference.json').read_text())


def source(lemma, symbol, grammar):
    return dict(lemma=lemma, symbol=symbol, grammar=grammar)


def generated(src):
    result = generate(src)[0]
    if result['generation']['status'] != 'generated': raise AssertionError(result)
    return result['generation']['readings'][0]


def words(src, **selector):
    return [f['stressed'] for f in generated(src)['forms'] if all(f['features'].get(k) == v for k, v in selector.items())]


class SpecialReferenceTests(unittest.TestCase):
    def test_coverage(self):
        self.assertEqual(len(REFERENCE['cases']), 8)
        self.assertEqual(len(REFERENCE['partners']), 60)
        self.assertEqual(sum('expected_corrected' in c for c in REFERENCE['partners']), 6)


def register():
    for n, case in enumerate(REFERENCE['cases']):
        def test(self, case=case):
            forms = generated(case['input'])['forms']
            for code, expected in case['expected'].items():
                grouped = {}
                for f in expected:
                    selector = verb_selector(code) if case['adb']['т'] == 'г' else code_selector(code, 'с')
                    if 'п2' in f:
                        selector['case'] = 'locative'
                        if f['п2']: selector['preposition'] = f['п2']
                    if 'р2' in f: selector['case'] = 'partitive'
                    key = json.dumps(selector, sort_keys=True)
                    status = {'фн': 'absent', 'фз': 'difficult', 'фп': 'tentative'}.get(f.get('ф'), 'normal')
                    grouped.setdefault(key, set()).add((f['с'] if status != 'absent' else None,
                        int(f['у']) if status != 'absent' else None, status))
                for selector, wanted in grouped.items():
                    selected = json.loads(selector)
                    actual = {(f['word']['text'] if f['word'] else None,
                        f['word']['accent_variants'][0]['primary'][0] if f['word'] else None, f['status'])
                        for f in forms if all(f['features'].get(k) == v for k, v in selected.items())
                        and ('case' in f['features']) == ('case' in selected)}
                    with self.subTest(code=code, selector=selector): self.assertEqual(actual, wanted)
        setattr(SpecialReferenceTests, f'test_original_paradigm_{n:02}', test)
    for n, case in enumerate(REFERENCE['partners']):
        def test(self, case=case):
            partner = generated(case['input'])['aspect_partner']
            self.assertEqual(partner['status'], 'generated', partner)
            self.assertEqual([w['stressed'] for w in partner['words']], [case.get('expected_corrected', case['expected'])])
        setattr(SpecialReferenceTests, f'test_original_partner_{n:02}', test)


register()


PATTERN = source('затоло́чь', 'св', '8b/b (-к-) △ буд. затолку́, затолчёт; прош. затоло́к, затолкла́; прич. действ. прош. затоло́кший; прич. страд. затолчённый')


class SpecialTests(unittest.TestCase):
    def test_noun_overrides_do_not_erase_regular_singular(self):
        src = source('брат', 'мо', '1a △ мн. бра́ть|я, -ев, -ям, -ями, -ях')
        self.assertEqual(words(src, case='genitive', number='singular'), ['бра́та'])
        self.assertEqual(words(src, case='accusative', number='plural'), ['бра́тьев'])

    def test_dative_override_supplies_instrumental_and_prepositional(self):
        src = source('брат', 'мо', '1a △ мн. бра́тья; Р. мн. бра́тьев; Д. мн. бра́тьям')
        self.assertEqual(words(src, case='instrumental', number='plural'), ['бра́тьями'])
        self.assertEqual(words(src, case='prepositional', number='plural'), ['бра́тьях'])

    def test_explicit_stress_in_suffix_replaces_stem_stress(self):
        src = source('друг', 'мо', '3c △ мн. дру́з|ья, -е́й, -ья́м, -ья́ми, -ья́х')
        self.assertEqual(words(src, case='genitive', number='plural'), ['друзе́й'])

    def test_unknown_exception_tail_is_not_silently_ignored(self):
        src = source('брат', 'мо', '1a △ мн. бра́тья; см. ещё неизвестное')
        result = generate(src)[0]
        self.assertEqual(result['status'], 'unsupported')
        self.assertEqual(result['generation']['status'], 'blocked')

    def test_html_register_note_stays_with_exception_form(self):
        src = source('брат', 'мо', '1a △ Р. мн. бра́тьев (<i>устар.</i>)')
        fs = generated(src)['forms']
        self.assertEqual([f['note'] for f in fs if f['features']['case'] == 'genitive' and f['features']['number'] == 'plural'], ['устар.'])

    def test_reflexive_exception_derives_correct_third_plural_postfix(self):
        src = source('затоло́чься', 'св', '8b/b (-к-) △ буд. затолку́сь, затолчётся')
        self.assertEqual(words(src, form='finite', tense='future', person=3, number='plural'), ['затолку́тся'])
        self.assertEqual(words(src, form='imperative', number='plural'), ['затолки́тесь'])

    def test_reference_does_not_lose_new_secondary_stress(self):
        payload = [source('со̀бра́т', 'мо', 'склон. см. брат'), source('брат', 'мо', '1a')]
        self.assertEqual(generate(payload)[0]['generation']['status'], 'blocked')

    def test_genitive_and_partitive_remain_distinct(self):
        src = source('са́хар', 'м', '1a, Р2')
        self.assertEqual(words(src, case='genitive', number='singular'), ['са́хара'])
        self.assertEqual(words(src, case='partitive'), ['са́хару'])

    def test_optional_locative_contains_both_variants_and_preposition(self):
        src = source('лес', 'м', '1c①, [П2(в)]')
        fs = generated(src)['forms']
        self.assertEqual(words(src, case='locative'), ['лесу́', 'ле́се'])
        self.assertTrue(all(f['features']['preposition'] == 'в' for f in fs if f['features']['case'] == 'locative'))

    def test_locative_e_yo_not_confused_with_ordinary_prepositional(self):
        src = source('край', 'м', '6c①, П2(на)')
        self.assertEqual(words(src, case='locative'), ['краю́'])
        self.assertEqual(words(src, case='prepositional', number='singular'), ['кра́е'])

    def test_verb_exception_changes_dependent_forms(self):
        self.assertEqual(words(PATTERN, form='finite', tense='future', person=2, number='singular'), ['затолчёшь'])
        self.assertEqual(words(PATTERN, form='imperative', number='singular'), ['затолки́'])
        self.assertEqual(words(PATTERN, form='finite', tense='past', gender='neuter'), ['затолкло́'])
        self.assertEqual(words(PATTERN, form='gerund', tense='past'), ['затоло́кши'])
        self.assertEqual(words(PATTERN, form='participle', voice='passive', tense='past',
                               gender='feminine', number='singular', case='genitive'), ['затолчённой'])

    def test_entirely_irregular_verb_has_no_regular_stem_guess(self):
        src = source('дать', 'св', 'Δa: буд. дам, дашь, даст, дади́м, дади́те, даду́т; повел. дай; прош. дал, дала́, да́ло, да́ли; прич. страд. да́нный')
        self.assertEqual(words(src, form='imperative'), ['да́й', 'да́йте'])
        self.assertEqual(words(src, form='gerund', tense='past'), ['да́в', 'да́вши'])
        self.assertEqual(words(src, form='finite', tense='future', person=1, number='plural'), ['дади́м'])

    def test_incomplete_irregular_verb_is_blocked(self):
        result = generate(source('дать', 'св', 'Δa: буд. дам'))[0]
        self.assertEqual(result['generation']['status'], 'blocked')
        self.assertEqual(result['generation']['readings'][0]['forms'], [])
        result = generate(source('дать', 'св', 'Δa: буд. дам, даст; повел. дай; прош. дал, дала́'))[0]
        self.assertEqual(result['generation']['status'], 'blocked')

    def test_exception_status_and_restriction(self):
        src = source('брат', 'мо', '1a, Р. мн. затрудн. △ Р. мн. бра́тьев')
        fs = generated(src)['forms']
        self.assertEqual([f['status'] for f in fs if f['features']['case'] == 'genitive' and f['features']['number'] == 'plural'], ['difficult'])

    def test_reference_forward_and_backward_with_prefix_replacement(self):
        alias = source('столо́чь', 'св', 'спряж. см. затоло́чь')
        for payload, index in (([alias, PATTERN], 0), ([PATTERN, alias], 1)):
            result = generate(payload)[index]
            self.assertEqual(result['generation']['status'], 'generated', result)
            fs = result['generation']['readings'][0]['forms']
            self.assertEqual([f['stressed'] for f in fs if f['features'] == {'form': 'finite', 'tense': 'future', 'person': 1, 'number': 'singular'}], ['столку́'])
            self.assertEqual([f['stressed'] for f in fs if f['features'] == {'form': 'finite', 'tense': 'past', 'gender': 'masculine', 'number': 'singular'}], ['столо́к'])

    def test_noun_reference(self):
        payload = [source('собра́т', 'мо', 'склон. см. брат'), source('брат', 'мо', '1a △ мн. бра́тья; Р. мн. бра́тьев; Д. мн. бра́тьям')]
        g = generate(payload)[0]['generation']
        self.assertEqual(g['status'], 'generated', g)
        self.assertIn('собра́тьев', [f['stressed'] for f in g['readings'][0]['forms']])

    def test_reference_requires_compatible_stress_and_suffix(self):
        for alias, pattern in ((source('сто́л', 'м', 'склон. см. слон'), source('слон', 'м', '1b')),
                               (source('сто́лик', 'м', 'склон. см. столбик'), source('столби́к', 'м', '3a'))):
            g = generate([alias, pattern])[0]['generation']
            self.assertEqual(g['status'], 'blocked')
            self.assertEqual(g['readings'][0]['diagnostics'][0]['code'], 'REFERENCE_UNSUPPORTED')

    def test_reference_to_failed_generation_blocks_dependent(self):
        payload = [source('запе́чь', 'св', 'спряж. см. испе́чь'), source('испе́чь', 'св', '8b')]
        self.assertEqual([x['generation']['status'] for x in generate(payload)], ['blocked', 'blocked'])

    def test_reference_chain_is_iterative(self):
        payload = [source('брат', 'мо', '1a')]
        for i in range(50):
            payload.append(source('со' * (i + 1) + 'бра́т', 'мо', 'склон. см. ' + 'со' * i + 'бра́т'))
        self.assertTrue(all(x['generation']['status'] == 'generated' for x in generate(list(reversed(payload)))))

    def test_explicit_partner_separate_from_forms(self):
        src = source('прочита́ть', 'св', '1a ◑ чита́ть')
        result = generate(src)
        self.assertEqual(len(result), 1)
        item = result[0]['generation']['readings'][0]
        self.assertEqual(item['aspect_partner']['words'][0]['stressed'], 'чита́ть')
        self.assertNotIn('чита́ть', [f['stressed'] for f in item['forms']])

    def test_partner_failure_does_not_erase_original_paradigm(self):
        src = source('чита́ть', 'нсв', '1a ◑16')
        result = generate(src)[0]['generation']
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['readings'][0]['status'], 'generated')
        self.assertTrue(result['readings'][0]['forms'])
        self.assertEqual(result['readings'][0]['aspect_partner']['status'], 'blocked')

    def test_supported_paragraphs_affect_forms(self):
        self.assertTrue(all(f['status'] == 'difficult' for f in generated(source('вя́заный', 'п', '1a §7'))['forms'] if f['features'].get('form') == 'short'))
        self.assertEqual(set(words(source('му́чить', 'нсв', '4a §16'), form='finite', tense='present', person=1, number='singular')), {'му́чу', 'му́чаю'})
        src = source('маха́ть', 'нсв', 'нп 6c//1a §13')
        fs = generated(src)['forms']
        self.assertEqual({f['stressed']: f['note'] for f in fs if f['features'] == {'form': 'finite', 'tense': 'present', 'person': 3, 'number': 'singular'}}, {'ма́шет': '', 'маха́ет': 'разг.'})

    def test_unimplemented_paragraph_is_diagnosed(self):
        for grammar in ('1a §999', '1a §12'):
            result = generate(source('стол', 'м', grammar))[0]
            self.assertEqual(result['readings'][0]['inflection']['paragraphs'], [int(grammar.split('§')[1])])
            self.assertEqual(result['generation']['status'], 'blocked')
            self.assertEqual(result['generation']['readings'][0]['forms'], [])

    def test_new_models_and_outputs_match_schemas_and_preserve_input(self):
        payload = [PATTERN, source('лес', 'м', '1c①, [П2(в)], Р2'), source('столкну́ть', 'св', '3b ◑I(-а́-)'), source('маха́ть', 'нсв', '6c//1a §13')]
        saved = copy.deepcopy(payload)
        normalized = analyze(payload)
        before = copy.deepcopy(normalized)
        output = generate_analyzed(normalized)
        self.assertEqual(payload, saved)
        self.assertEqual(normalized, before)
        self.assertEqual(generate(payload), output)
        av = Draft202012Validator(json.loads((ROOT / 'schemas/analysis.schema.json').read_text()))
        gv = Draft202012Validator(json.loads((ROOT / 'schemas/generation.schema.json').read_text()))
        for article in output:
            generation = article.pop('generation')
            av.validate(article)
            gv.validate(generation)


if __name__ == '__main__':
    unittest.main()
