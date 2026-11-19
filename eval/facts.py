"""Do numbers and quantities in the translation match the official English? (independent of any model)"""
import json, re, sys
from common import by_article
W = {'one': 1, 'once': 1, 'two': 2, 'twice': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
     'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'ninety': 90, 'hundred': 100}
def nums(t):
    t = t.lower().replace('twenty-five', '25').replace('twenty five', '25').replace('forty-five', '45')
    out = [int(x) for x in re.findall(r'(?<![\w.])(\d{1,4})(?![\w])', t)]
    out += [W[w] for w in re.findall(r'\b(' + '|'.join(W) + r')\b', t)]
    return out
blocks, ref = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for f in sys.argv[3:]:
    tr = {}
    for c in json.load(open(f))['chunks']: tr.update(c.get('translations', {}))
    arts = {}
    for a, b in by_article(blocks):
        if a and b['id'] in tr: arts.setdefault(a, []).append(tr[b['id']])
    hit = miss = extra = 0; misses = []
    for a, parts in arts.items():
        r = [n for n in nums(ref[str(a)]) if n > 1]; h = [n for n in nums(' '.join(parts)) if n > 1]
        for n in set(r):
            k = min(r.count(n), h.count(n)); hit += k; miss += r.count(n) - k
            if r.count(n) > k: misses.append(f'{a}:{n}')
        extra += sum(max(0, h.count(n) - r.count(n)) for n in set(h))
    print(f'{f:42s} quantities matched {hit}/{hit + miss}  missing: {" ".join(misses)}  extra: {extra}')
