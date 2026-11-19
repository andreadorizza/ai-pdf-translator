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
GROUP = 6


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


def crop(work, p, paragraphs):
    """The paragraph with the whole text column and about one line above and below, zoomed when small."""
    im = Image.open(Path(work) / 'ocr' / f"p{p['page']:03d}.png")
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
    by_id = {p['id']: p for p in paragraphs}
    scan = [i for i in todo if by_id.get(i, {}).get('kind') == 'scan']
    (work / 'scancheck').mkdir(exist_ok=True)
    files = []
    for n, i in enumerate(range(0, len(scan), GROUP), 1):
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


def number_problems(source, english, prof):
    """Figures in the source that the English does not contain, as digits or (for small numbers) words."""
    src = prof.ascii_digits(source)
    en = english.lower().replace(',', '')
    have = set(_runs(en))
    words = {str(v) for w, v in WORDS.items() if re.search(rf'\b{w}\b', en)}
    months = {str(i + 1) for i, m in enumerate(MONTHS) if m in en}
    missing = []
    # Figures inside Latin words (CO2, N2O, tCO2e) are names, often misread by OCR: skip them.
    for tok in re.findall(r'(?<![A-Za-z\d])(?:\d[\d.,/:-]*\d|\d)(?![A-Za-z\d])', src):
        if re.fullmatch(r'\d{1,2}[.)]?', tok) and tok == src.strip()[:len(tok)]:
            continue                       # a list number at the start
        date = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', tok)
        for j, run in enumerate(_runs(tok.replace(',', '').replace('.', '') if not date else tok)):
            if run in have or run in words or (date and j == 1 and run in months):
                continue
            missing.append(run)
    return missing
