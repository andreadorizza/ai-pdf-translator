"""Doubts: reasons to distrust the main reading of a paragraph, found without any model.

readings_differ  where the second OCR reading disagrees with the main one
low_confidence   words the OCR itself was unsure of
not_in_dictionary  text the language's dictionary cannot explain
numbers          figures, dates and references (list numbers excluded)
junk_characters  characters that belong to neither the script nor ordinary punctuation
"""
import difflib
import re
from functools import lru_cache
from pathlib import Path

from .ocr import DPI, tesseract_words


def diff_spans(a, b, ctx=4):
    a, b = a.replace(' ', ''), b.replace(' ', '')
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != 'equal':
            out.append(f'…{a[max(0, i1 - ctx):i1]}[{a[i1:i2]}|{b[j1:j2]}]{a[i2:i2 + ctx]}…')
    return out


@lru_cache(maxsize=1)
def _laonlp():
    from laonlp.tokenize import word_tokenize
    return word_tokenize


def non_words(text, prof):
    """Runs of 2+ single-letter tokens: text the dictionary cannot split into words."""
    if prof.get('dictionary') != 'laonlp':
        return []
    bad, run = [], ''
    for tok in _laonlp()(text):
        if len(tok) == 1 and prof.in_script(tok):
            run += tok
        else:
            if len(run) >= 2:
                bad.append(run)
            run = ''
    if len(run) >= 2:
        bad.append(run)
    return bad


def _inside(words, bbox):
    s = DPI / 72
    x0, y0, x1, y1 = (v * s for v in bbox)
    # Tesseract lists words in reading order; keep it.
    return [w for w in words if x0 <= (w['box'][0] + w['box'][2]) / 2 <= x1 and y0 <= (w['box'][1] + w['box'][3]) / 2 <= y1]


def numbers(text, prof):
    t = prof.ascii_digits(text)
    return [x for x in re.findall(r'\d[\d.,/:-]*', t) if not re.fullmatch(r'\d{1,2}[.,)]?', x)]


def find(paragraph, prof, work):
    """Doubts for one paragraph; scan paragraphs also get their second reading."""
    text = prof.norm(paragraph['text'])
    found = []
    if paragraph['kind'] == 'scan':
        base = Path(work) / 'ocr' / f"p{paragraph['page']:03d}"
        main = _inside(_words(f'{base}.main.tsv'), paragraph['bbox'])
        second = _inside(_words(f'{base}.second.tsv'), paragraph['bbox']) if Path(f'{base}.second.tsv').exists() else []
        alt = prof.norm(' '.join(w['text'] for w in second))
        if alt:
            paragraph['second_reading'] = alt
            d = diff_spans(text, alt)
            if d:
                found.append({'type': 'readings_differ', 'spans': d})
        low = [prof.norm(w['text']) for w in main if 0 <= w['conf'] < 50]
        if low:
            found.append({'type': 'low_confidence', 'words': low})
        junk = sum(1 for c in text if not (prof.in_script(c) or c.isalnum() or c.isspace() or c in '.,;:()/-–"\'%'))
        if junk >= 3:
            found.append({'type': 'junk_characters', 'count': junk})
    if paragraph.get('role') == 'picture' and paragraph.get('conf', 100) < 75:
        found.append({'type': 'low_confidence', 'words': [text]})
    nw = non_words(text.replace(' ', ''), prof)
    if nw:
        found.append({'type': 'not_in_dictionary', 'spans': nw})
    nums = numbers(text, prof)
    if nums:
        found.append({'type': 'numbers', 'values': nums})
    return found


@lru_cache(maxsize=64)
def _words(path):
    return tuple(tesseract_words(path)) if Path(path).exists() else ()
