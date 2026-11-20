"""Build: merge translations, scan checks and fixes; write the translated PDF, a Markdown copy and the review list."""
import json
import re
from pathlib import Path

from . import layout
from .check import load_translations, number_problems
from .layout import TITLE, key


# A scan-check note on a corrected item usually explains the correction; keep those that express doubt.
DOUBT = re.compile(r'unclear|uncertain|not sure|low confidence|moderate confidence|could be|may be|might|verify|check|'
                   r'illegible|hard to read|guess', re.I)


def load_job(work):
    work = Path(work)
    return json.loads((work / 'job.json').read_text()), json.loads((work / 'paragraphs.json').read_text())


def merge(work, paragraphs, prof=None):
    work = Path(work)
    english, checks = load_translations(work)
    checked, unreadable = {}, {}
    for f in sorted((work / 'scancheck').glob('*.result.json')):
        for pid, r in json.loads(f.read_text()).items():
            if r.get('english') and pid in english:
                english[pid] = r['english']
            checked[pid] = r
            if r.get('unreadable'):
                unreadable[pid] = r
    fixes = work / 'fixes.json'
    fixed = json.loads(fixes.read_text()) if fixes.exists() else {}
    for pid, en in fixed.items():
        if isinstance(en, str):
            english[pid] = en
    for p in paragraphs:            # cells of figures are kept as they are
        if p.get('copy') and p['id'] not in english:
            english[p['id']] = p['text']
    norm = (lambda s: ''.join(prof.norm(s).split())) if prof else (lambda s: ''.join(s.split()))
    by_text = {}                    # text translated once (a running header) serves every copy of it
    for p in paragraphs:
        if p['id'] in english:
            by_text.setdefault(norm(p['text']), english[p['id']])
    for p in paragraphs:
        if p['id'] not in english and norm(p['text']) in by_text:
            english[p['id']] = by_text[norm(p['text'])]
    return english, checks, checked, unreadable, fixed


def build(work, prof, threads=4, review_only=False):
    work = Path(work)
    job, paragraphs = load_job(work)
    english, checks, checked, unreadable, fixed = merge(work, paragraphs, prof)
    lookup = {(p['page'], key(p['text'])): english[p['id']] for p in paragraphs if p['id'] in english}
    stem = Path(job['source']).stem
    mono, dual = work / f'{stem}.en.pdf', work / f'{stem}.bilingual.pdf'
    source, picture_labels = job['searchable'], []
    if (work / 'pictures' / 'index.json').exists():     # text in pictures: redrawn in a copy before the layout pass
        from . import pictures
        source = work / 'source.pictures.pdf'
        picture_labels = pictures.apply(work, job['searchable'], source)
    missing_in_layout = [] if review_only else layout.render(source, job['pages'], job['scan_pages'], prof,
                                                             work, lookup, mono, dual, threads)

    review = []
    for p in paragraphs:
        pid, en = p['id'], english.get(p['id'])
        if pid in fixed:
            continue
        if en is None:
            review.append((p, 'Not translated', ''))
            continue
        if pid in unreadable:
            review.append((p, 'The scan check could not read the scan', unreadable[pid].get('source_read', '')))
        nums = number_problems(p['text'], en, prof)
        if nums:
            review.append((p, 'Figures in the source missing from the English', ', '.join(nums)))
        if pid in checks and pid not in checked:
            review.append((p, 'The translator was unsure and no scan check was done', '; '.join(checks[pid])))
        elif pid in checks and not checked[pid].get('changed') and pid not in unreadable:
            review.append((p, 'The translator was unsure; the scan check found the page prints it this way',
                           '; '.join(checks[pid] + [checked[pid].get('note') or '']).strip('; ')))
        elif checked.get(pid, {}).get('note') and pid not in unreadable and (
                not checked[pid].get('changed') or DOUBT.search(checked[pid]['note'])):
            review.append((p, 'Note from the scan check', checked[pid]['note']))
    unsure = {}                     # unsure labels in pictures: one item per page, each label with its English
    for x in picture_labels:
        if x['unsure']:
            unsure.setdefault(x['page'], []).append(f"{x['source']} → {x['english']}")
    for page, items in sorted(unsure.items()):
        review.append(({'id': 'pictures', 'page': page, 'text': f'{len(items)} labels'},
                       'Labels in pictures the reader was unsure of', '; '.join(items)))
    for page, text in missing_in_layout:
        review.append(({'id': '?', 'page': page, 'text': text}, 'Found in the layout but not in the paragraph list', ''))

    seen, unique = set(), []         # the same problem in repeated text (a cell on several pages) is listed once
    for p, why, detail in review:
        k = (why, ''.join(p['text'].split()), detail)
        if k not in seen:
            seen.add(k)
            unique.append((p, why, detail))
    review = unique
    lines = [f'# Review list: {Path(job["source"]).name}', '',
             f'{len(review)} items. Check each against the source; to correct one, add its id and the full corrected '
             'English to `fixes.json` in this folder ({"p009_03": "English"}) and run `ai-pdf-translator apply '
             f'{work}`. No model runs again.', '']
    for p, why, detail in review:
        lines += [f"## {p['id']} (page {p['page']}): {why}", '', f"- Source: {p['text'][:400]}",
                  f"- English: {english.get(p['id'], '')[:600]}"]
        if detail:
            lines.append(f'- Detail: {detail}')
        lines.append('')
    (work / 'review.md').write_text('\n'.join(lines))

    write_markdown(work, stem, paragraphs, english, prof, picture_labels)
    return {'pdf': str(mono), 'bilingual': str(dual), 'markdown': str(work / f'{stem}.en.md'),
            'source_markdown': str(work / f'{stem}.{prof.code}.md'),
            'bilingual_markdown': str(work / f'{stem}.bilingual.md'),
            'review': str(work / 'review.md'), 'review_items': len(review),
            'translated': sum(p['id'] in english for p in paragraphs), 'paragraphs': len(paragraphs)}


def _table(rows):
    """Markdown table from {(row, col): text}."""
    nrows = max(r for r, _ in rows) + 1
    ncols = max(c for _, c in rows) + 1
    cell = lambda r, c: rows.get((r, c), '').replace('|', '\\|').replace('\n', ' ')
    lines = ['| ' + ' | '.join(cell(0, c) for c in range(ncols)) + ' |', '|' + ' --- |' * ncols]
    lines += ['| ' + ' | '.join(cell(r, c) for c in range(ncols)) + ' |' for r in range(1, nrows)]
    return '\n'.join(lines)


def _blocks(paragraphs, text_of, pictures=None):
    """Page by page: paragraphs and labels as text, the cells of each table as one Markdown table, then the labels
    read from the page's pictures."""
    out, page, tables = [], None, {}
    pictures = pictures or {}

    def picture_block(n):
        if pictures.get(n):
            out.append('Labels in pictures: ' + ' · '.join(pictures[n]))

    for p in paragraphs:
        if p['page'] != page:
            if page is not None:
                picture_block(page)
            page = p['page']
            out.append(f'*Page {page}*')
        t = text_of(p)
        if not t:
            continue
        if p.get('role') == 'cell':
            key = (p['page'], p.get('table'))
            if key not in tables:
                tables[key] = {}
                out.append(tables[key])
            tables[key][(p['row'], p['col'])] = t
        else:
            out.append(t)
    if page is not None:
        picture_block(page)
    return '\n\n'.join(_table(b) if isinstance(b, dict) else b for b in out) + '\n'


def write_markdown(work, stem, paragraphs, english, prof, picture_labels=()):
    """The source text, the English, and both together, in reading order with page marks. No model involved."""
    work = Path(work)
    src = lambda p: prof.norm(p['text']).strip()
    en = lambda p: english.get(p['id'], '').strip()
    by_page_src, by_page_en = {}, {}
    for x in picture_labels:
        by_page_src.setdefault(x['page'], []).append(x['source'])
        by_page_en.setdefault(x['page'], []).append(x['english'])
    (work / f'{stem}.{prof.code}.md').write_text(_blocks(paragraphs, src, by_page_src))
    (work / f'{stem}.en.md').write_text(_blocks(paragraphs, en, by_page_en))
    both = []
    page = None
    for p in paragraphs:
        if p['page'] != page:
            page = p['page']
            both.append(f'## Page {page}')
        role = '' if p.get('role', 'paragraph') == 'paragraph' else f" ({p['role']})"
        both.append(f"> {src(p)}{role}\n\n{en(p) or '*(not translated)*'}")
        nxt = paragraphs[paragraphs.index(p) + 1]['page'] if p is not paragraphs[-1] else None
        if nxt != page:
            both += [f"> {x['source']} (picture)\n\n{x['english']}" for x in picture_labels if x['page'] == page]
    (work / f'{stem}.bilingual.md').write_text('\n\n'.join(both) + '\n')
