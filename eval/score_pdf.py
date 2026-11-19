"""Score translated PDFs from any tool against the human English, article by article.

Reads the text of each translated PDF, splits it at "Article N" headings, and reports
chrF++ (sacrebleu) and the numbers check on the articles every PDF has in common.
usage: score_pdf.py <reference_en.json> <label>=<pdf>[:first-last] ...   (pages are 1-based)
"""
import json, re, sys, unicodedata
import fitz, sacrebleu

W = {'one': 1, 'once': 1, 'two': 2, 'twice': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
     'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20, 'thirty': 30, 'forty': 40,
     'fifty': 50, 'sixty': 60, 'ninety': 90, 'hundred': 100}
HEAD = re.compile(r'(?:^|\n)\s*Articles?\s+(\d{1,3})\b')
# PDFMathTranslate's output shows normal punctuation, but its text layer maps it to U+1C7E–U+1C9F;
# map it back so the score measures the translation, not the text layer. NFKC also undoes ﬁ/ﬂ ligatures.
TEXT_LAYER = str.maketrans({'ᲈ': '.', 'ᲆ': ',', 'Ე': ':', 'ᲇ': '-', 'Ვ': ';',
                            'ᲁ': "'", 'ᲂ': '(', 'ᲃ': ')', '᲋': 'fi', '᱾': ',', 'Ლ': ' '})


def clean(t):
    return unicodedata.normalize('NFKC', t.translate(TEXT_LAYER))


def nums(t):
    t = t.lower().replace('twenty-five', '25').replace('twenty five', '25').replace('forty-five', '45')
    out = [int(x) for x in re.findall(r'(?<![\w.])(\d{1,4})(?![\w])', t)]
    out += [W[w] for w in re.findall(r'\b(' + '|'.join(W) + r')\b', t)]
    return [n for n in out if n > 1]


def articles(pdf, first, last):
    """Split the text at headings whose numbers go up by 1 to 3, so cross-references are not taken as headings."""
    doc = fitz.open(pdf)
    text = clean("\n".join(doc[i].get_text() for i in range(first - 1, last)))
    arts, cur, start = {}, None, 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        if cur is None or cur < n <= cur + 3:
            if cur is not None: arts[cur] = text[start:m.start()]
            cur, start = n, m.start()
    if cur is not None: arts[cur] = text[start:]
    return {a: ' '.join(t.split()) for a, t in arts.items()}


ref = json.load(open(sys.argv[1]))
runs = []
for arg in sys.argv[2:]:
    label, spec = arg.split('=', 1)
    path, _, rng = spec.partition(':')
    n = len(fitz.open(path))
    first, last = map(int, rng.split('-')) if rng else (1, n)
    runs.append((label, articles(path, first, last)))
common = sorted(set.intersection(*(set(a) for _, a in runs)) & {int(k) for k in ref})
print(f'articles in common: {len(common)} ({common[0]}–{common[-1]})' if common else 'no articles in common')
for label, arts in runs:
    hyp = [arts[a] for a in common]; refs = [ref[str(a)] for a in common]
    chrf = sacrebleu.corpus_chrf(hyp, [refs], word_order=2).score
    hit = tot = 0
    for h, r in zip(hyp, refs):
        rn, hn = nums(r), nums(h)
        for x in set(rn):
            hit += min(rn.count(x), hn.count(x)); tot += rn.count(x)
    print(f'{label:28s} found {len(arts):3d} articles   chrF++ {chrf:5.1f}   numbers {hit}/{tot}')
