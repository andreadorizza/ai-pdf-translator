"""Turn each OCR source for pages 6 and 15 into blocks, so the same translator and the same scorer can compare them."""
import json, re, unicodedata
from langs import LANGS
L = LANGS['lo']
def norm(t):
    t = unicodedata.normalize('NFC', t)
    for a, b in L['normalize']: t = t.replace(a, b)
    return t
def from_text(t, page):
    t = re.sub(r'<BLOCK>\w+\[[\d, ]+\]<FORK>', '\n\n', t)
    t = re.sub(r'<[^>]+>|\*\*|^#+\s*|^\s*[-|]\s*', '', t, flags=re.M)
    paras = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n|\n(?=\s*(?:ມາດຕາ|\d{1,2}\.)\s)', t)]
    return [{'id': f'p{page:03d}_b{i:02d}', 'page': page, 'text': norm(p), 'alt_text': '', 'flags': []} for i, p in enumerate(paras) if p]
R = '../results'
tess = [b for b in json.load(open('run1/blocks.json')) if b['page'] in (6, 15)]
sources = {
    'tesseract_with_hints': tess,
    'tesseract_plain': [dict(b, alt_text='', flags=[]) for b in tess],
    'claude_vision': from_text(open(f'{R}/claude/decree_p006.md').read(), 6) + from_text(open(f'{R}/claude/decree_p015.md').read(), 15),
    'unlimited_ocr_2': from_text(open(f'{R}/unlimited-ocr-2/decree_p006.md').read(), 6) + from_text(open(f'{R}/unlimited-ocr-2/decree_p015.md').read(), 15),
}
for k, v in sources.items():
    json.dump(v, open(f'run1/ocrcmp/{k}.blocks.json', 'w'), ensure_ascii=False, indent=1)
    print(k, len(v), 'blocks', sum(len(b['text']) for b in v), 'chars')
