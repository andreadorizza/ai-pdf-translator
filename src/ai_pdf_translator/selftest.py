"""Self-test: translate pages of a public Lao decree that has a human English translation, and score the result.

The decree on carbon credits (Lao PDR, 2025) has the Lao on pages 1-28 and an English version on pages 29-56.
Default sample: pages 5-8 (articles 1-9). --full: pages 5-24 (articles 1-66).
Scores are independent of any model: chrF++ against the human English, and the figures in it.
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pymupdf

SHA256 = '57d665ffac0d9bd499e605d16777d98076a77d66da73b53717fe2905cc3ab529'
SAMPLE, FULL = '5-8', '5-24'
REFERENCE_PAGES = (29, 56)
PASS_CHRF, PASS_NUMBERS = 60.0, 0.95
NUM_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
             'ten': 10, 'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20, 'thirty': 30, 'forty': 40,
             'fifty': 50, 'sixty': 60, 'ninety': 90, 'hundred': 100}
HEAD = re.compile(r'(?:^|\n)\s*Articles?\s+(\d{1,3})\b')


def check_source(pdf):
    digest = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()
    if digest != SHA256:
        print(f'Warning: this is not the copy of the decree the scores were set on (sha256 {digest[:12]}…).')


def reference(pdf):
    """The decree's English, by article. Some spans use a font whose codes are shifted by 29; decode them."""
    import wordninja
    d = pymupdf.open(pdf)

    def fix(t):
        if sum(c.strip() != '' for c in t) < 6:
            return t
        shifted = ''.join(chr(ord(c) + 29) if 0x21 <= ord(c) <= 0x5D else c for c in t)
        low = lambda s: sum(c.islower() for c in s) / max(1, sum(c.isalpha() for c in s))
        if low(t) < 0.3 and low(shifted) > 0.7:
            return ' '.join(wordninja.split(shifted)) if ' ' not in t.strip() or len(t) > 15 else shifted
        return t

    lines = [''.join(fix(s['text']) for s in l['spans'])
             for i in range(REFERENCE_PAGES[0] - 1, REFERENCE_PAGES[1])
             for b in d[i].get_text('dict')['blocks'] for l in b.get('lines', [])]
    text = re.sub(r'\n\s*\d+\s*\n', '\n', '\n'.join(lines))
    parts = re.split(r'\n\s*(Articles?\s+\d+)\b', '\n' + text)
    arts = {}
    for head, body in zip(parts[1::2], parts[2::2]):
        body = re.split(r'\n\s*(?:Chapter|Part)\s+[IVXLC\d]+\b', body)[0]
        arts.setdefault(int(head.split()[1]), re.sub(r'\s+', ' ', head + ' ' + body).strip())
    return arts


def articles(pdf, pages):
    doc = pymupdf.open(pdf)
    text = unicodedata.normalize('NFKC', '\n'.join(doc[p - 1].get_text() for p in pages))
    arts, cur, start = {}, None, 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        if cur is None or cur < n <= cur + 3:      # headings go up; a cross-reference is not a heading
            if cur is not None:
                arts[cur] = text[start:m.start()]
            cur, start = n, m.start()
    if cur is not None:
        arts[cur] = text[start:]
    return {a: ' '.join(t.split()) for a, t in arts.items()}


def _nums(t):
    t = t.lower().replace('twenty-five', '25').replace('twenty five', '25').replace('forty-five', '45')
    out = [int(x) for x in re.findall(r'(?<![\w.])(\d{1,4})(?![\w])', t)]
    out += [NUM_WORDS[w] for w in re.findall(r'\b(' + '|'.join(NUM_WORDS) + r')\b', t)]
    return [n for n in out if n > 1]


def score(work):
    import sacrebleu
    work = Path(work)
    job = json.loads((work / 'job.json').read_text())
    ref = reference(job['source'])
    pdf = work / f"{Path(job['source']).stem}.en.pdf"
    got = articles(pdf, job['pages'])
    common = sorted(a for a in got if a in ref)
    expected = sorted(a for a in ref if a <= max(common, default=0) and a >= min(common, default=1))
    hyp, refs = [got[a] for a in common], [ref[a] for a in common]
    chrf = sacrebleu.corpus_chrf(hyp, [refs], word_order=2).score if common else 0.0
    hit = tot = 0
    for h, r in zip(hyp, refs):
        rn, hn = _nums(r), _nums(h)
        for x in set(rn):
            hit += min(rn.count(x), hn.count(x))
            tot += rn.count(x)
    share = hit / tot if tot else 0.0
    ok = chrf >= PASS_CHRF and share >= PASS_NUMBERS and len(common) == len(expected)
    usage = json.loads((work / 'usage.json').read_text()) if (work / 'usage.json').exists() else {}
    result = {'pass': ok, 'chrf': round(chrf, 1), 'numbers': [hit, tot], 'articles': [len(common), len(expected)],
              'usage': usage, 'minutes': job.get('minutes')}
    (work / 'self-test.json').write_text(json.dumps(result, indent=1))
    tokens = (f"{usage.get('input_tokens', 0):,} in / {usage.get('output_tokens', 0):,} out tokens"
              if usage else 'tokens: see your agent')
    return [f"Self-test {'PASS' if ok else 'FAIL'} (Lao → English, {len(common)} of {len(expected)} articles)",
            f'chrF++ {chrf:.1f} against the human English (pass ≥ {PASS_CHRF:.0f}; our reference run: 66)',
            f'Figures matched {hit}/{tot} ({share:.0%}, pass ≥ {PASS_NUMBERS:.0%})',
            f"{tokens}, {job.get('minutes', '?')} min"]
