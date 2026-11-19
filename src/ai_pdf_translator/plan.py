"""Paragraph ids, sections, term candidates and batches: the files the translators read."""
import collections
import json
import re
from importlib import resources
from pathlib import Path

BATCH_CHARS = 12000     # source characters per batch, whole sections only: each subagent has a fixed cost, so fewer is cheaper


def number_paragraphs(records, prof):
    """Give each paragraph an id (page and position) and its section; drop exact repeats on a page."""
    out, seen, per_page = [], set(), collections.Counter()
    section = None
    for r in records:
        if not r['text'].strip() or (r['page'], ''.join(r['text'].split())) in seen:
            continue
        seen.add((r['page'], ''.join(r['text'].split())))
        n = per_page[r['page']]
        per_page[r['page']] += 1
        s = prof.section(r['text'])
        if s is not None:
            section = s
        out.append(dict(r, id=f"p{r['page']:03d}_{n:02d}", section=section))
    return out


# Numbered headings and chapter words: good places to end a batch in documents without "Article N".
SOFT_BREAK = re.compile(r'^\s*(\d+(\.\d+)*\.?\s+\S|ບົດທີ|ພາກທີ|ໝວດທີ|Chapter|Part)')


def batches(paragraphs, prof, limit=BATCH_CHARS):
    """Whole sections per batch; at a numbered heading if a section runs long; anywhere past 1.5x the limit."""
    groups, cur, size = [], [], 0
    for p in paragraphs:
        new_section = prof.section(p['text']) is not None or SOFT_BREAK.match(p['text'])
        if cur and ((size > limit and new_section) or size > limit * 1.5):
            groups.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += prof.count(p['text']) or len(p['text'])
    if cur:
        groups.append(cur)
    return groups


def term_candidates(paragraphs, prof, limit=150):
    """Phrases of 2-4 dictionary words that repeat in the document, plus the definitions section if there is one."""
    if prof.get('dictionary') != 'laonlp':
        return {'phrases': [], 'definitions': []}
    from laonlp.tokenize import word_tokenize
    counts = collections.Counter()
    stop = set(prof.get('stopwords', []))
    for p in paragraphs:
        toks = [t for t in word_tokenize(prof.norm(p['text']).replace(' ', '')) if prof.count(t) >= 2]
        for n in (2, 3, 4):
            for i in range(len(toks) - n + 1):
                gram = toks[i:i + n]
                if gram[0] not in stop and gram[-1] not in stop:
                    counts[''.join(gram)] += 1
    phrases = [w for w, c in counts.most_common() if c >= 3 and len(w) >= 6]
    kept = []
    for w in phrases:                       # drop a phrase inside a longer kept phrase with the same count
        if not any(w in k and counts[k] >= counts[w] * 0.8 for k in kept):
            kept.append(w)
        if len(kept) >= limit:
            break
    definitions = []
    pat = prof.get('definitions_heading')
    if pat:
        start = next((i for i, p in enumerate(paragraphs) if re.search(pat, prof.norm(p['text']))), None)
        if start is not None:
            sec = paragraphs[start]['section']
            definitions = [p['text'] for p in paragraphs[start:] if p['section'] == sec][:40]
    return {'phrases': [{'source': w, 'count': counts[w]} for w in kept], 'definitions': definitions}


def hints(p):
    out = {}
    if p.get('second_reading') and p['second_reading'].replace(' ', '') != p['text'].replace(' ', ''):
        out['second_reading'] = p['second_reading']
    for f in p.get('doubts', []):
        if f['type'] == 'readings_differ':
            out['differences'] = f['spans'][:12]
        elif f['type'] == 'low_confidence':
            out['unsure_words'] = f['words'][:12]
        elif f['type'] == 'not_in_dictionary':
            out['not_in_dictionary'] = f['spans'][:12]
    return out


def write_files(work, paragraphs, prof, batch_chars=BATCH_CHARS):
    """Instruction files and term candidates; then the batches (without terms until the term list exists)."""
    work = Path(work)
    for d in ('batches', 'translations', 'terms'):
        (work / d).mkdir(exist_ok=True)
    for name in ('TRANSLATOR.md', 'TERMS.md', 'SCANCHECK.md'):
        text = resources.files('ai_pdf_translator.prompts').joinpath(name).read_text()
        (work / name).write_text(text.replace('{language}', prof.name))
    cands = term_candidates(paragraphs, prof)
    (work / 'terms' / 'candidates.json').write_text(json.dumps(
        {'language': prof.name, 'instructions': 'TERMS.md', 'output': 'terms/terms.json', **cands},
        ensure_ascii=False, indent=1))
    return write_batches(work, paragraphs, prof, batch_chars), cands


def write_batches(work, paragraphs, prof, batch_chars=BATCH_CHARS):
    """One self-contained file per batch: the instructions, the terms that occur in it, and its paragraphs.
    A subagent reads this one file and writes one. Batches already translated are left alone."""
    work = Path(work)
    t = work / 'terms' / 'terms.json'
    terms = json.loads(t.read_text()) if t.exists() else {}
    instructions = (work / 'TRANSLATOR.md').read_text()
    groups = batches(paragraphs, prof, batch_chars)
    for old in (work / 'batches').glob('[0-9][0-9][0-9].json'):
        if not (work / 'translations' / old.name).exists():
            old.unlink()
    for i, g in enumerate(groups, 1):
        name = f'{i:03d}'
        if (work / 'translations' / f'{name}.json').exists():
            continue
        text = ''.join(''.join(prof.norm(p['text']).split()) for p in g)
        used = {k: v for k, v in terms.items() if ''.join(prof.norm(k).split()) in text}
        b = {'batch': name, 'output': f'translations/{name}.json', 'instructions': instructions,
             'terms': used if terms else 'no term list yet',
             'paragraphs': [dict({'id': p['id'], 'page': p['page'], 'text': prof.norm(p['text'])}, **hints(p))
                            for p in g]}
        (work / 'batches' / f'{name}.json').write_text(json.dumps(b, ensure_ascii=False, indent=1))
    return groups
