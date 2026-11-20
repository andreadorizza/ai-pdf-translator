"""Which paragraphs get a scan check, their crops, and the numbers check (no model involved)."""
import json
import re
from pathlib import Path

from PIL import Image

from .ocr import DPI

WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
         'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17,
         'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
         'seventy': 70, 'eighty': 80, 'ninety': 90, 'hundred': 100, 'thousand': 1000}
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october',
          'november', 'december']
GROUP = 12      # items per scan-check file: each subagent has a fixed cost, each crop adds little


def load_translations(work):
    english, checks = {}, {}
    for f in sorted((Path(work) / 'translations').glob('*.json')):
        data = json.loads(f.read_text())
        english.update(data.get('translations', {}))
        for c in data.get('check', []):
            checks.setdefault(c['id'], []).append(f"{c.get('source', c.get('lao', ''))}: {c.get('why', '')}".strip(': '))
    return english, checks


def to_check(paragraphs, english, checks):
    """Translator doubts, plus scan paragraphs whose OCR shows numbers or junk."""
    out = {k: list(v) for k, v in checks.items() if k in english}
    for p in paragraphs:
        if p['kind'] == 'scan' and p['id'] in english and any(
                f['type'] in ('junk_characters', 'numbers') for f in p.get('doubts', [])):
            out.setdefault(p['id'], []).append('automatic: the OCR shows numbers or junk characters here')
    return out


def page_image(work, page):
    """The page at 300 DPI: the OCR render for scan pages, rendered now for text pages."""
    png = Path(work) / 'ocr' / f'p{page:03d}.png'
    if not png.exists():
        import pymupdf
        png.parent.mkdir(exist_ok=True)
        source = json.loads((Path(work) / 'job.json').read_text())['source']
        pymupdf.open(source)[page - 1].get_pixmap(dpi=DPI).save(png)
    return Image.open(png)


def crop(work, p, paragraphs):
    """The paragraph with the whole text column and about one line above and below, zoomed when small."""
    im = page_image(work, p['page'])
    s = DPI / 72
    same = [o['bbox'] for o in paragraphs if o['page'] == p['page'] and o.get('bbox')]
    left, right = min(b[0] for b in same), max(b[2] for b in same)
    x0, y0, x1, y1 = p['bbox']
    c = im.crop((max(0, int((left - 8) * s)), max(0, int((y0 - 14) * s)),
                 min(im.width, int((right + 8) * s)), min(im.height, int((y1 + 14) * s))))
    if c.width < 1400:
        c = c.resize((int(c.width * 1.5), int(c.height * 1.5)), Image.LANCZOS)
    path = Path(work) / 'crops' / f"{p['id']}.png"
    path.parent.mkdir(exist_ok=True)
    c.save(path)
    return path


def make_scan_checks(work, paragraphs):
    work = Path(work)
    english, checks = load_translations(work)
    todo = to_check(paragraphs, english, checks)
    (work / 'scancheck').mkdir(exist_ok=True)
    for f in (work / 'scancheck').glob('*.result.json'):       # checked already: do not check again
        for pid in json.loads(f.read_text()):
            todo.pop(pid, None)
    by_id = {p['id']: p for p in paragraphs}
    # Text pages too: a text layer can lack what the page shows (figures drawn without text behind them).
    scan = [i for i in todo if by_id.get(i, {}).get('bbox')]
    (work / 'scancheck').mkdir(exist_ok=True)
    files = []
    first = 1 + max((int(f.name[:3]) for f in (work / 'scancheck').glob('[0-9][0-9][0-9].json')), default=0)
    for n, i in enumerate(range(0, len(scan), GROUP), first):
        items = []
        for pid in scan[i:i + GROUP]:
            p = by_id[pid]
            items.append({'id': pid, 'image': str(crop(work, p, paragraphs).relative_to(work)), 'source': p['text'],
                          'english': english[pid], 'doubt': todo[pid]})
        f = work / 'scancheck' / f'{n:03d}.json'
        f.write_text(json.dumps({'check': f'{n:03d}', 'instructions': 'SCANCHECK.md',
                                 'output': f'scancheck/{n:03d}.result.json', 'items': items},
                                ensure_ascii=False, indent=1))
        files.append(f)
    return files, [i for i in todo if i not in scan]


def _runs(text):
    return [r.lstrip('0') or '0' for r in re.findall(r'\d+', text)]


ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth', 'eleventh',
            'twelfth', 'thirteenth', 'fourteenth', 'fifteenth', 'sixteenth', 'seventeenth', 'eighteenth', 'nineteenth',
            'twentieth']
ROMAN = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}


def _roman(s):
    total = 0
    for a, b in zip(s, s[1:] + ' '):
        v = ROMAN[a]
        total += -v if b != ' ' and ROMAN.get(b, 0) > v else v
    return total


UNITS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
         'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
         'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
         'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
SCALES = {'hundred': 100, 'thousand': 1000, 'million': 1000000, 'billion': 1000000000}


def _word_numbers(low):
    """Numbers written in words, compound ones included: "one hundred and eighty" is 180."""
    out, total, current, seen = [], 0, 0, False
    for tok in re.findall(r"[a-z]+", low.replace('-', ' ')) + ['.']:
        if tok in UNITS:
            current += UNITS[tok]
            seen = True
        elif tok in SCALES and seen:
            if SCALES[tok] == 100:
                current *= 100
            else:
                total += current * SCALES[tok]
                current = 0
        elif tok == 'and' and seen:
            continue
        else:
            if seen:
                out.append(total + current)
            total, current, seen = 0, 0, False
    return out


def _english_numbers(english):
    """Every number the English states: digits, number words, ordinals, Roman numerals, months."""
    en = english.replace(',', '')
    low = en.lower()
    have = set(_runs(en)) | {str(n) for n in _word_numbers(low)}
    have |= {str(v) for w, v in WORDS.items() if re.search(rf'\b{w}\b', low)}
    have |= {str(i + 1) for i, w in enumerate(ORDINALS) if re.search(rf'\b{w}\b', low)}
    have |= {str(_roman(r)) for r in re.findall(r'\b([IVXLC]{1,6})\b', en)}
    return have, {str(i + 1) for i, m in enumerate(MONTHS) if m in low}


def number_problems(source, english, prof):
    """Figures in the source that the English does not contain, as digits, words, ordinals or Roman numerals."""
    src = re.sub(r'(?<=\d) (?=\d)', '', prof.ascii_digits(source))     # "3 0" from split glyph runs is 30
    have, months = _english_numbers(english)
    missing = []
    # Figures inside Latin words (CO2, N2O, tCO2e) are names, often misread by OCR: skip them.
    for tok in re.findall(r'(?<![A-Za-z\d])(?:\d[\d.,/:-]*\d|\d)(?![A-Za-z\d])', src):
        if re.fullmatch(r'\d{1,2}[.)]?', tok) and tok == src.strip()[:len(tok)]:
            continue                       # a list number at the start
        date = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', tok)
        if date:
            parts = _runs(tok)
            if any(r not in have and not (j == 1 and r in months) for j, r in enumerate(parts)):
                missing.append(tok)
            continue
        parts = _runs(tok)
        merged = _runs(tok.replace(',', '').replace('.', ''))   # "1.000" or "1,000" may be written 1000
        if all(_stated(r, have) for r in parts) or all(_stated(r, have) for r in merged):
            continue
        missing.append(tok)
    return missing


def _stated(run, have):
    """A figure is stated if the English has it; a figure printed twice by the PDF ("1616") counts once."""
    half = len(run) // 2
    return run in have or (len(run) % 2 == 0 and half and run[:half] == run[half:] and run[:half] in have)
