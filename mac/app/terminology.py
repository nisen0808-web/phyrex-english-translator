"""Bounded, context-sensitive terminology hints for the public distribution."""
from functools import lru_cache
import json
import re

MAX_GLOSSARY_TERMS = 1000
TRANSLATION_MAX_TERMS = 40
TRANSLATION_MAX_CHARS = 3200
ASR_MAX_TERMS = 20
ASR_MAX_CHARS = 450
CORE_HINTS = ('Federal Reserve', 'FOMC', 'federal funds rate', 'basis points',
              'PCE', 'CPI', 'nonfarm payrolls', 'JOLTS', 'labor market',
              'disinflation', 'neutral rate', 'Treasury securities', 'SOFR',
              'IORB', 'quantitative tightening')


def validate_glossary(glossary):
    if (not isinstance(glossary, dict) or len(glossary) > MAX_GLOSSARY_TERMS
            or not all(isinstance(k, str) and isinstance(v, str)
                       and 0 < len(k.strip()) <= 120 and 0 < len(v.strip()) <= 200
                       for k, v in glossary.items())):
        raise ValueError('术语库最多 1000 条，每条英文术语和中文译法不可为空，分别不超过 120 和 200 个字符。')
    return glossary


def normalized(text):
    # Punctuation, hyphens and apostrophes vary in speech recognition output.
    return ' '.join(re.findall(r'[a-z0-9]+', text.casefold()))


@lru_cache(maxsize=2048)
def term_pattern(term):
    words = normalized(term).split()
    if not words:
        return None
    last = words[-1]
    ending = re.escape(last)
    # Support common noun plurals; never match inside another word (CPI/spice).
    if len(last) > 3 and last.isalpha() and not last.endswith('s'):
        if last.endswith('y') and last[-2] not in 'aeiou':
            ending = re.escape(last[:-1]) + r'(?:y|ies)'
        elif last.endswith(('ch', 'sh', 'x', 'z')):
            ending += r'(?:es)?'
        else:
            ending += r's?'
    prefix = ' '.join(re.escape(w) for w in words[:-1])
    return re.compile(r'(?<![a-z0-9])' + (prefix + ' ' if prefix else '') + ending + r'(?![a-z0-9])')


def ranked_matches(source, context, keys):
    texts = (normalized(source), normalized(context[-900:]))
    ranked = []
    for index, key in enumerate(keys):
        pattern = term_pattern(key)
        if pattern is None:
            continue
        for priority, text in enumerate(texts):
            matches = list(pattern.finditer(text))
            if matches:
                match = matches[-1]
                ranked.append((priority, -len(normalized(key)), -match.start(), index, key))
                break
    return [item[-1] for item in sorted(ranked)]


def translation_glossary(source, context, glossary, profile='fed'):
    if profile != 'fed':
        return {}
    selected = {}
    for key in ranked_matches(source, context, glossary):
        candidate = {**selected, key: glossary[key]}
        if len(json.dumps(candidate, ensure_ascii=False)) <= TRANSLATION_MAX_CHARS:
            selected = candidate
        if len(selected) == TRANSLATION_MAX_TERMS:
            break
    return selected


def recognition_hotwords(context, keywords, profile='fed'):
    if profile != 'fed':
        return ''
    available = set(keywords)
    related = ranked_matches(context[-900:], '', keywords)[:12]
    candidates = related + [key for key in CORE_HINTS if key in available]
    selected = []
    seen = set()
    for key in candidates:
        identity = normalized(key)
        if identity in seen or len(', '.join(selected + [key])) > ASR_MAX_CHARS:
            continue
        selected.append(key)
        seen.add(identity)
        if len(selected) == ASR_MAX_TERMS:
            break
    return ', '.join(selected)
