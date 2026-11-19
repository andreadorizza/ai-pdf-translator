"""Build: merge translations, scan checks and fixes; write the translated PDF, a Markdown copy and the review list."""
import json
from pathlib import Path

from . import layout
from .check import load_translations, number_problems
from .layout import TITLE, key


def load_job(work):
    work = Path(work)
    return json.loads((work / 'job.json').read_text()), json.loads((work / 'paragraphs.json').read_text())


def merge(work, paragraphs):
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
    return english, checks, checked, unreadable, fixed


def build(work, prof, threads=4):
    work = Path(work)
    job, paragraphs = load_job(work)
    english, checks, checked, unreadable, fixed = merge(work, paragraphs)
    lookup = {(p['page'], key(p['text'])): english[p['id']] for p in paragraphs if p['id'] in english}
    stem = Path(job['source']).stem
    mono, dual = work / f'{stem}.en.pdf', work / f'{stem}.bilingual.pdf'
    missing_in_layout = layout.render(job['searchable'], job['pages'], job['scan_pages'], prof, work, lookup,
                                      mono, dual, threads)

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
    for page, text in missing_in_layout:
        review.append(({'id': '?', 'page': page, 'text': text}, 'Found in the layout but not in the paragraph list', ''))

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

    md = []
    for p in paragraphs:
        en = english.get(p['id'])
        if en:
            m = TITLE.match(en)
            md.append(f'## {m.group(1)}\n\n{m.group(3)}'.strip() if m and len(m.group(1)) < 140 else en)
    (work / f'{stem}.en.md').write_text('\n\n'.join(md) + '\n')
    return {'pdf': str(mono), 'bilingual': str(dual), 'markdown': str(work / f'{stem}.en.md'),
            'review': str(work / 'review.md'), 'review_items': len(review),
            'translated': sum(p['id'] in english for p in paragraphs), 'paragraphs': len(paragraphs)}
