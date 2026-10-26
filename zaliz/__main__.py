"""Командная строка: JSON из файла или stdin, результат разбора в JSON."""
import argparse
import json
from pathlib import Path
import sys

from . import InputError, __version__, analyze, generate


def _invalid_constant(value):
    raise ValueError(f'{value} не является допустимой константой JSON.')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Разбор словарных описаний lemma / symbol / grammar')
    parser.add_argument('file', nargs='?', help='JSON-файл; без аргумента или с - читается stdin')
    parser.add_argument('-o', '--output', help='Записать результат в JSON-файл вместо stdout')
    parser.add_argument('--generate', action='store_true', help='Построить словоформы после разбора')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    try:
        content = (Path(args.file).read_text(encoding='utf-8-sig')
                   if args.file and args.file != '-' else sys.stdin.read().removeprefix('\ufeff'))
        payload = json.loads(content, parse_constant=_invalid_constant)
        results = generate(payload) if args.generate else analyze(payload)
        output = json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output:
            Path(args.output).write_text(output, encoding='utf-8')
        else:
            sys.stdout.write(output)
        ready = all(item['generation']['status'] == 'generated' for item in results) if args.generate else all(item['status'] == 'parsed' for item in results)
        return 0 if ready else 1
    except (OSError, ValueError, InputError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
