"""ai-pdf-translator: the toolbox a coding agent uses to translate scanned PDFs, step by step.

  setup          check Tesseract, its models and the layout model; say how to install what is missing
  prepare PDF    sort pages, read scans twice, find paragraphs and doubts, write term candidates and batches
  batches WORK   after the term list: rewrite each batch with the terms it uses
  status WORK    what is done and what is left
  crops WORK     after translation: crops of the scan for the paragraphs in doubt, in scan-check files
  build WORK     merge everything; write the translated PDF, a bilingual PDF, Markdown and the review list
  apply WORK     after a person's fixes in WORK/fixes.json: rebuild (no model runs, except for corrected source text)
  translate WORK headless: do the translation and scan check through a provider API, then build
  self-test PDF  translate pages of the Lao decree that has a human English version, and score the result
  install-skill  copy the agent skill into .claude/skills and .agents/skills
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

USAGE_HINT = 'Run "ai-pdf-translator setup" first if this is a new machine.'


def parse_pages(spec, n):
    if not spec:
        return list(range(1, n + 1))
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += range(int(a), int(b or a) + 1)
    return [p for p in out if 1 <= p <= n]


def _write_job(work, job):
    (Path(work) / 'job.json').write_text(json.dumps(job, indent=1))


def prepare(pdf, lang='lo', pages=None, work=None, psm=4, threads=4, batch_chars=None):
    import pymupdf
    from . import doubts, langs, layout, ocr, plan
    prof = langs.load(lang)
    src = Path(pdf).resolve()
    work = Path(work or src.with_suffix('.translation'))
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()
    doc = pymupdf.open(src)
    pages = parse_pages(pages, len(doc))
    kinds = ocr.page_kinds(doc, prof)
    scan = [p for p in pages if kinds[p - 1] == 'scan']
    print(f'Reading {len(scan)} scan pages twice ({prof.tesseract_main}, {prof.get("tesseract_second")})', flush=True)
    ocr.read_pages(src, scan, prof, work, psm=psm, workers=threads)
    for p in ocr.scanned_target_pages(scan, prof, work):
        kinds[p - 1] = 'target'
    scan = [p for p in scan if kinds[p - 1] == 'scan']
    todo = [p for p in pages if kinds[p - 1] in ('text', 'scan')]
    if not todo:
        raise SystemExit('No page to translate: every page is blank or already in English.')
    searchable = work / 'source.searchable.pdf'
    ocr.searchable_pdf(src, scan, work, searchable)
    print('Finding paragraphs (PDFMathTranslate layout model)', flush=True)
    records = layout.record(searchable, todo, scan, prof, work, threads)
    paragraphs = plan.number_paragraphs(records, prof)
    for p in paragraphs:
        p['doubts'] = doubts.find(p, prof, work)
    (work / 'paragraphs.json').write_text(json.dumps(paragraphs, ensure_ascii=False, indent=1))
    groups, cands = plan.write_files(work, paragraphs, prof, batch_chars or plan.BATCH_CHARS)
    job = {'source': str(src), 'lang': lang, 'pages': todo, 'scan_pages': scan, 'searchable': str(searchable),
           'kinds': {k: [p for p in pages if kinds[p - 1] == k] for k in ('text', 'scan', 'target', 'blank')},
           'batch_chars': batch_chars or plan.BATCH_CHARS, 'started': started, 'prepared_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    _write_job(work, job)
    chars = sum(prof.count(p['text']) for p in paragraphs)
    doubtful = sum(bool(p['doubts']) for p in paragraphs)
    k = job['kinds']
    print(f'\nPrepared {work}\n'
          f'Pages: {len(k["scan"])} scan, {len(k["text"])} text, {len(k["target"])} already English, {len(k["blank"])} blank\n'
          f'Paragraphs: {len(paragraphs)} ({chars:,} {prof.name} characters), {doubtful} with doubts\n'
          f'Batches: {len(groups)} (batches/001.json … {len(groups):03d}.json); term candidates: {len(cands["phrases"])}\n'
          f'Next: term list (TERMS.md → terms/terms.json), then "ai-pdf-translator batches {work}", '
          f'then one translator per batch.')
    return work


def rebatch(work):
    from . import langs, plan
    work = Path(work)
    job = json.loads((work / 'job.json').read_text())
    paragraphs = json.loads((work / 'paragraphs.json').read_text())
    groups = plan.write_batches(work, paragraphs, langs.load(job['lang']), job.get('batch_chars', plan.BATCH_CHARS))
    has_terms = (work / 'terms' / 'terms.json').exists()
    print(f'{len(groups)} batches in {work / "batches"}' + ('' if has_terms else ' (no term list yet)'))


def status(work):
    work = Path(work)
    batches = sorted((work / 'batches').glob('*.json'))
    left = [b.name for b in batches if not (work / json.loads(b.read_text())['output']).exists()]
    checks = sorted((work / 'scancheck').glob('[0-9][0-9][0-9].json')) if (work / 'scancheck').exists() else []
    left_checks = [c.name for c in checks if not (work / json.loads(c.read_text())['output']).exists()]
    job = json.loads((work / 'job.json').read_text())
    built = (work / f"{Path(job['source']).stem}.en.pdf").exists()
    print(f"Term list: {'done' if (work / 'terms' / 'terms.json').exists() else 'missing (TERMS.md)'}\n"
          f"Batches translated: {len(batches) - len(left)}/{len(batches)}" + (f" (left: {', '.join(left)})" if left else '') + '\n'
          f"Scan checks done: {len(checks) - len(left_checks)}/{len(checks)}" + (f" (left: {', '.join(left_checks)})" if left_checks else '') + '\n'
          f"Built: {'yes' if built else 'no'}")


def crops(work):
    from .build import load_job
    from .check import make_scan_checks
    _, paragraphs = load_job(work)
    files, text_only = make_scan_checks(work, paragraphs)
    print(f'Scan checks: {len(files)} files ({", ".join(f.name for f in files) or "none"}), '
          f'follow SCANCHECK.md for each.' + (f' {len(text_only)} doubts on text pages go to the review list.' if text_only else ''))
    return files


def build(work, threads=4):
    from . import langs
    from .build import build as _build
    work = Path(work)
    job = json.loads((work / 'job.json').read_text())
    r = _build(work, langs.load(job['lang']), threads)
    job['minutes'] = round((time.time() - job['started']) / 60, 1)
    _write_job(work, job)
    print(f"Translated {r['translated']}/{r['paragraphs']} paragraphs\n"
          f"PDF: {r['pdf']}\nBilingual PDF: {r['bilingual']}\nMarkdown: {r['markdown']}\n"
          f"Review list: {r['review']} ({r['review_items']} items)")
    return r


def apply(work, threads=4):
    work = Path(work)
    fixes = work / 'fixes.json'
    if not fixes.exists():
        raise SystemExit(f'No {fixes}. Write {{"<paragraph id>": "<corrected English>"}} there first.')
    data = json.loads(fixes.read_text())
    source_fixes = {k: v['source'] for k, v in data.items() if isinstance(v, dict) and v.get('source')}
    if source_fixes:
        paragraphs = {p['id']: p for p in json.loads((work / 'paragraphs.json').read_text())}
        n = len(list((work / 'batches').glob('fix-*.json'))) + 1
        name = f'fix-{n:03d}'
        b = {'batch': name, 'language': json.loads((work / 'job.json').read_text())['lang'], 'instructions': 'TRANSLATOR.md',
             'terms': 'terms/terms.json', 'output': f'translations/{name}.json',
             'paragraphs': [{'id': k, 'page': paragraphs[k]['page'], 'text': v} for k, v in source_fixes.items()]}
        (work / 'batches' / f'{name}.json').write_text(json.dumps(b, ensure_ascii=False, indent=1))
        for k in source_fixes:
            del data[k]
        fixes.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(f'{len(source_fixes)} paragraphs have corrected source text: translate batches/{name}.json '
              f'(TRANSLATOR.md), then run "ai-pdf-translator build {work}".')
        return
    build(work, threads)


def translate(work, service, model, check_model=None, base_url=None, threads=4):
    from . import services
    work = Path(work)
    svc = services.Service(service, model, base_url)
    chk = services.Service(service, check_model, base_url) if check_model and check_model != model else svc
    print(f'Term list ({model})', flush=True)
    services.terms(work, svc)
    rebatch(work)
    print(f'Translating batches ({model})', flush=True)
    services.translate_batches(work, svc, threads)
    files = crops(work)
    if files:
        print(f'Scan check ({chk.model})', flush=True)
        services.scan_check(work, chk, files, threads)
    usage = {k: svc.usage[k] + (chk.usage[k] if chk is not svc else 0) for k in svc.usage}
    (work / 'usage.json').write_text(json.dumps(usage, indent=1))
    return build(work, threads)


def setup():
    from . import langs
    ok = True
    tess = shutil.which('tesseract')
    plat = 'brew' if sys.platform == 'darwin' else 'apt'
    prof = langs.load('lo')
    hint = f"brew install {prof.install['brew']}" if plat == 'brew' else f"sudo apt-get install -y {prof.install['apt']}"
    if not tess:
        print(f'Missing: Tesseract. Install: {hint}')
        ok = False
    else:
        have = set(subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True).stdout.split()[1:])
        need = set(prof.tesseract_main.split('+')) | {prof.tesseract_second}
        if need - have:
            print(f'Missing Tesseract models: {", ".join(sorted(need - have))}. Install: {hint}')
            ok = False
        else:
            print(f'Tesseract: ok ({", ".join(sorted(need))})')
    try:
        from .layout import _model
        _model()
        print('Layout model: ok')
    except Exception as e:      # first run downloads it from Hugging Face
        print(f'Layout model: failed to load ({e})')
        ok = False
    print('Ready.' if ok else 'Fix the items above, then run setup again.')
    return ok


def install_skill(agent='all', where='project'):
    src = Path(__file__).parent / 'skill'
    if not src.exists():
        src = Path(__file__).parents[2] / 'skills' / 'ai-pdf-translator'
    base = Path.home() if where == 'global' else Path.cwd()
    targets = {'claude': ['.claude/skills'], 'codex': ['.agents/skills'], 'opencode': ['.agents/skills'],
               'all': ['.claude/skills', '.agents/skills']}[agent]
    for t in targets:
        dst = base / t / 'ai-pdf-translator'
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f'Installed {dst}')


def self_test(pdf=None, full=False, work=None, service=None, model=None, check_model=None, base_url=None, score_only=None):
    from . import selftest
    if score_only:
        print('\n'.join(selftest.score(score_only)))
        return
    selftest.check_source(pdf)
    work = prepare(pdf, 'lo', selftest.FULL if full else selftest.SAMPLE,
                   work or Path(pdf).resolve().with_name('self-test.translation'))
    if service:
        translate(work, service, model, check_model, base_url)
        print('\n'.join(selftest.score(work)))
    else:
        print(f'\nNow translate as for any document, build, then run: ai-pdf-translator self-test --score {work}')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='ai-pdf-translator', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('setup')
    p = sub.add_parser('prepare')
    p.add_argument('pdf')
    p.add_argument('--lang', default='lo', help='language code (built in: lo) or a profile file')
    p.add_argument('--pages', help='e.g. 1-20,25')
    p.add_argument('--work', help='work folder (default: next to the PDF, <name>.translation)')
    p.add_argument('--psm', type=int, default=4, help='Tesseract page segmentation mode')
    p.add_argument('--batch-chars', type=int, help='source characters per batch (default 12000)')
    for name in ('batches', 'status', 'crops', 'build', 'apply'):
        sub.add_parser(name).add_argument('work')
    p = sub.add_parser('translate')
    p.add_argument('work')
    p.add_argument('--service', required=True, choices=['anthropic', 'openai'])
    p.add_argument('--model', required=True)
    p.add_argument('--check-model', help='model for the scan check (must read images); default: --model')
    p.add_argument('--base-url')
    p = sub.add_parser('self-test')
    p.add_argument('pdf', nargs='?')
    p.add_argument('--full', action='store_true')
    p.add_argument('--work')
    p.add_argument('--score', metavar='WORK')
    p.add_argument('--service', choices=['anthropic', 'openai'])
    p.add_argument('--model')
    p.add_argument('--check-model')
    p.add_argument('--base-url')
    p = sub.add_parser('install-skill')
    p.add_argument('--agent', default='all', choices=['all', 'claude', 'codex', 'opencode'])
    p.add_argument('--global', dest='where', action='store_const', const='global', default='project')
    a = ap.parse_args(argv)
    if a.cmd == 'setup':
        sys.exit(0 if setup() else 1)
    elif a.cmd == 'prepare':
        prepare(a.pdf, a.lang, a.pages, a.work, a.psm, batch_chars=a.batch_chars)
    elif a.cmd == 'batches':
        rebatch(a.work)
    elif a.cmd == 'status':
        status(a.work)
    elif a.cmd == 'crops':
        crops(a.work)
    elif a.cmd == 'build':
        build(a.work)
    elif a.cmd == 'apply':
        apply(a.work)
    elif a.cmd == 'translate':
        translate(a.work, a.service, a.model, a.check_model, a.base_url)
    elif a.cmd == 'self-test':
        if not a.score and not a.pdf:
            ap.error('self-test needs the decree PDF, or --score WORK')
        self_test(a.pdf, a.full, a.work, a.service, a.model, a.check_model, a.base_url, a.score)
    elif a.cmd == 'install-skill':
        install_skill(a.agent, a.where)


if __name__ == '__main__':
    main()
