"""Score translations against the official English, article by article (chrF++ and BLEU, sacrebleu)."""
import json, sys
import sacrebleu
from common import by_article
blocks, ref = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
rows = []
for f in sys.argv[3:]:
    tr = {}
    for c in json.load(open(f))['chunks']:
        tr.update(c.get('translations', {}))
    arts = {}
    for a, b in by_article(blocks):
        if a and b['id'] in tr: arts.setdefault(a, []).append(tr[b['id']])
    common = sorted(a for a in arts if str(a) in ref)
    hyp = [' '.join(arts[a]) for a in common]; refs = [ref[str(a)] for a in common]
    chrf = sacrebleu.corpus_chrf(hyp, [refs], word_order=2).score
    bleu = sacrebleu.corpus_bleu(hyp, [refs]).score
    per = {a: round(sacrebleu.sentence_chrf(h, [r], word_order=2).score, 1) for a, h, r in zip(common, hyp, refs)}
    rows.append((f, len(common), round(chrf, 1), round(bleu, 1), per))
for f, n, c, b, per in rows:
    print(f'{f:40s} articles={n:3d}  chrF++={c:5.1f}  BLEU={b:5.1f}')
print('per article chrF++:')
for f, n, c, b, per in rows:
    print(f'  {f:38s}', ' '.join(f'{a}:{v}' for a, v in per.items()))
