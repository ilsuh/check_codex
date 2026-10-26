"""Проверки командной строки: настоящий процесс и JSON на входе/выходе."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from zaliz import analyze

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, data=None):
    return subprocess.run([sys.executable, '-m', 'zaliz', *args], input=data,
                          capture_output=True, text=True, encoding='utf-8', cwd=ROOT)


class CliTests(unittest.TestCase):
    def test_special_examples_generate_successfully(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'forms.json')
            process = run_cli('--generate', 'examples/special.json', '-o', path)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(Path(path).read_text())
            self.assertEqual(len(result), 7)
            self.assertTrue(all(x['generation']['status'] == 'generated' for x in result))

    def test_failed_partner_returns_partial_with_nonzero_exit(self):
        process = run_cli('--generate', data=json.dumps({'lemma':'чита́ть','symbol':'нсв','grammar':'1a ◑16'}))
        self.assertEqual(process.returncode, 1, process.stderr)
        result = json.loads(process.stdout)[0]['generation']
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['readings'][0]['forms'])
        self.assertEqual(result['readings'][0]['aspect_partner']['status'], 'blocked')

    def test_generate_single_from_stdin(self):
        source = {'lemma': 'столбе́ц', 'symbol': 'м', 'grammar': '5*b'}
        process = run_cli('--generate', data=json.dumps(source))
        self.assertEqual(process.returncode, 0, process.stderr)
        generation = json.loads(process.stdout)[0]['generation']
        self.assertEqual(generation['status'], 'generated')
        self.assertEqual([f['stressed'] for f in generation['readings'][0]['forms']][:3],
                         ['столбе́ц', 'столбца́', 'столбцу́'])

    def test_generate_group_preserves_missing_dependencies(self):
        process = run_cli('--generate', 'examples/group.json')
        self.assertEqual(process.returncode, 1, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(len(result), 77)
        self.assertEqual(result[5]['generation']['status'], 'generated')
        self.assertEqual(result[4]['generation']['status'], 'generated')
        self.assertEqual(result[46]['generation']['status'], 'blocked')

    def test_generation_exit_status_is_independent_of_successful_analysis(self):
        source = {'lemma': 'печь', 'symbol': 'нсв', 'grammar': '8b'}
        process = run_cli('--generate', data=json.dumps(source))
        self.assertEqual(process.returncode, 1)
        result = json.loads(process.stdout)[0]
        self.assertEqual(result['status'], 'parsed')
        self.assertEqual(result['generation']['status'], 'blocked')

    def test_single_from_file(self):
        process = run_cli('examples/single.json')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout),
                         json.loads((ROOT / 'tests/fixtures/single.expected.json').read_text()))
        self.assertEqual(process.stderr, '')

    def test_single_line_from_stdin(self):
        source = {'lemma': 'столбе́ц', 'symbol': 'м', 'grammar': '5*b'}
        process = run_cli(data=json.dumps(source, ensure_ascii=False))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), analyze(source))

    def test_dash_and_unicode_json_escapes(self):
        source = {'lemma': 'ма́стерская', 'symbol': 'ж', 'grammar': '<п 1a>'}
        process = run_cli('-', data=json.dumps(source, ensure_ascii=True))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), analyze(source))

    def test_group_returns_nonzero_for_missing_patterns(self):
        process = run_cli('examples/group.json')
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertEqual(json.loads(process.stdout),
                         json.loads((ROOT / 'tests/fixtures/group.expected.json').read_text()))
        self.assertEqual(process.stderr, '')

    def test_bom_and_output_file(self):
        source = {'lemma': 'кни́га', 'symbol': 'ж', 'grammar': '3a'}
        with tempfile.TemporaryDirectory() as directory:
            input_file = Path(directory) / 'вход.json'
            output_file = Path(directory) / 'результат.json'
            input_file.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8-sig')
            process = run_cli(str(input_file), '-o', str(output_file))
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, '')
            self.assertEqual(json.loads(output_file.read_text()), analyze(source))
        process = run_cli(data='\ufeff' + json.dumps(source))
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_per_article_error_still_returns_json(self):
        process = run_cli(data='{"lemma":"","symbol":"м","grammar":"1a"}')
        self.assertEqual(process.returncode, 1)
        self.assertEqual(json.loads(process.stdout)[0]['status'], 'invalid')

    def test_bad_documents(self):
        for content in ('{bad', '42', '[{} , null]', '{"entries":[]}',
                        '{"lemma":"стол","symbol":"м","grammar":NaN}'):
            with self.subTest(content=content):
                process = run_cli(data=content)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(process.stdout, '')
                self.assertIn('Ошибка:', process.stderr)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            process = run_cli(str(Path(directory) / 'отсутствует.json'))
            self.assertEqual(process.returncode, 2)
            self.assertIn('Ошибка:', process.stderr)

    def test_empty_array(self):
        process = run_cli(data='[]')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), [])
        self.assertEqual(run_cli('--generate', data='[]').returncode, 0)

    def test_search_is_not_a_supported_command(self):
        process = run_cli('--search', 'стол')
        self.assertEqual(process.returncode, 2)


if __name__ == '__main__':
    unittest.main()
