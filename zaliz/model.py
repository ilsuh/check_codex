"""Создание объектов согласованной внутренней модели версии 1.

Модель сериализуется обычным JSON. Её внешняя форма описана в
schemas/analysis.schema.json; генерация словоформ от неё отделена.
"""
from copy import deepcopy


class InputError(ValueError):
    """Входной документ не является статьёй или массивом статей."""


class WordError(ValueError):
    """Некорректное написание или положение знака ударения."""


def result(source: dict, index: int) -> dict:
    return {
        'schema_version': 1, 'source_index': index, 'source': deepcopy(source),
        'effective_lemma': None, 'inherited_from': None, 'headword': None,
        'status': 'parsed', 'readings': [], 'annotations': [],
        'unparsed': [], 'diagnostics': [],
    }


def reading(pos: str, gender=None, animacy='not_applicable') -> dict:
    family = {'noun': 'substantive', 'adjective': 'adjectival',
              'verb': 'verbal', 'surname': 'pronominal'}.get(pos, 'none')
    genders = (['masculine', 'feminine', 'neuter'] if pos == 'adjective'
               else ['masculine', 'feminine'] if pos == 'surname'
               else [gender] if gender else [])
    return {
        'part_of_speech': pos, 'gender': gender, 'agreement_genders': genders,
        'animacy': animacy,
        'number_scope': ('both' if pos in ('noun', 'adjective', 'surname')
                         else 'not_applicable' if pos in ('adverb', 'verb')
                         else 'unspecified'),
        'inflection': {
            'kind': 'invariable' if pos == 'adverb' else 'explicit' if pos == 'pronoun' else 'regular',
            'family': family, 'pattern_gender': None, 'pattern_animacy': None,
            'index': None, 'fleeting_vowel': False, 'special_alternation': False,
            'consonant_alternation': None,
            'stress': {'full': None, 'short': None, 'past': None},
        },
        'verb': None, 'deviations': [], 'restrictions': [],
        'explicit_forms': [], 'relations': [], 'reference': None,
    }


def diagnose(item: dict, status: str, code: str, message: str) -> None:
    item['status'] = status
    item['diagnostics'].append({'code': code, 'message': message})


def restriction(selector: dict, status: str, note: str) -> dict:
    return {'selector': selector, 'status': status, 'note': note}


def relation(target: dict, *sources: dict) -> dict:
    return {'target': target, 'same_as': list(sources)}
