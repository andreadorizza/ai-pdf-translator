"""Official English text of the decree, split by article (pages 29-56)."""
import json, re, sys
import pymupdf
pdf, out = sys.argv[1], sys.argv[2]
d = pymupdf.open(pdf)
import wordninja
def fix_span(t):
    """Some spans use a font whose codes are shifted by 29 ('FKDQJH' = 'change'); decode them and restore spaces."""
    letters = [c for c in t if c.strip()]
    if len(letters) < 6: return t
    shifted = ''.join(chr(ord(c) + 29) if 0x21 <= ord(c) <= 0x5D else c for c in t)
    low = lambda s: sum(c.islower() for c in s) / max(1, sum(c.isalpha() for c in s))
    if low(t) < 0.3 and low(shifted) > 0.7:
        return ' '.join(wordninja.split(shifted)) if ' ' not in t.strip() or len(t) > 15 else shifted
    return t
def page_text(p):
    out = []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            out.append(''.join(fix_span(s['text']) for s in l['spans']))
    return '\n'.join(out)
text = '\n'.join(page_text(d[i]) for i in range(28, 56))
text = re.sub(r'\n\s*\d+\s*\n', '\n', text)          # page numbers
parts = re.split(r'\n\s*(Articles?\s+\d+)\b', '\n' + text)
arts = {}
for head, body in zip(parts[1::2], parts[2::2]):
    n = int(head.split()[1])
    body = re.split(r'\n\s*(?:Chapter|Part)\s+[IVXLC\d]+\b', body)[0]   # drop a following chapter heading
    arts.setdefault(n, re.sub(r'\s+', ' ', head + ' ' + body).strip())
json.dump(arts, open(out, 'w'), ensure_ascii=False, indent=1)
print(len(arts), 'articles:', min(arts), '-', max(arts), '| missing:', sorted(set(range(1, max(arts) + 1)) - set(arts)))
print(arts[35][:400])
