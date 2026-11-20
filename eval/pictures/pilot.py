"""Pilot of the picture step (src/ai_pdf_translator/pictures.py) on five pictures of the Lao groundwater report.

  prepare   find the labels, write contact sheets and a numbered overlay per picture (for a person to count misses)
  render    after a vision subagent wrote results/pNNN.json: redraw the pictures, a PDF of the five pages, before/after

usage: pilot.py prepare|render <report.pdf> <out_dir>
"""
import json
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from ai_pdf_translator import langs
from ai_pdf_translator.pictures import _detector, contact_sheets, find_labels, font_path, pictures_on, redraw

PAGES = [12, 18, 22, 37, 59]


def main(cmd, pdf, out):
    out = Path(out)
    prof = langs.load('lo')
    doc = pymupdf.open(pdf)
    if cmd == 'prepare':
        det = _detector()
        manifest = {}
        for pno in PAGES:
            pic = max(pictures_on(doc, pno), key=lambda p: p['image'].width * p['image'].height)
            t = time.time()
            labels = find_labels(pic['image'], prof, det)
            sheets, items = contact_sheets(pic['image'], labels, out / 'sheets', f'p{pno:03d}')
            ov = pic['image'].copy()
            d = ImageDraw.Draw(ov)
            f = ImageFont.load_default(size=14)
            for it in items:
                b = it['box']
                d.rectangle(b, outline=(255, 0, 0), width=2)
                d.text((b[0], b[1] - 15), str(it['n']), fill=(255, 0, 0), font=f)
            (out / 'overlays').mkdir(parents=True, exist_ok=True)
            ov.save(out / 'overlays' / f'p{pno:03d}.png')
            manifest[pno] = {'xref': pic['xref'], 'labels': [it['box'] for it in items],
                             'sheets': [str(s.relative_to(out)) for s in sheets], 'seconds': round(time.time() - t, 1)}
            print(f'page {pno}: {len(labels)} labels, {len(sheets)} sheets, {manifest[pno]["seconds"]} s')
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    elif cmd == 'render':
        manifest = json.loads((out / 'manifest.json').read_text())
        fp = font_path()
        new = pymupdf.open(pdf)        # same object numbers as the source, so the pictures' xrefs match
        rows = []
        for pno_s, m in manifest.items():
            pno = int(pno_s)
            res = json.loads((out / 'results' / f'p{pno:03d}.json').read_text())
            pic = next(p for p in pictures_on(doc, pno) if p['xref'] == m['xref'])
            img = redraw(pic['image'], m['labels'], res, fp)
            buf = __import__('io').BytesIO()
            img.save(buf, 'JPEG', quality=90)
            new[pno - 1].replace_image(m['xref'], stream=buf.getvalue())
            translated = sum(1 for r in res.values() if not r.get('keep') and (r.get('english') or '').strip())
            rows.append((pno, len(m['labels']), translated))
            both = Image.new('RGB', (pic['image'].width * 2 + 20, pic['image'].height), 'white')
            both.paste(pic['image'], (0, 0))
            both.paste(img, (pic['image'].width + 20, 0))
            (out / 'before_after').mkdir(parents=True, exist_ok=True)
            both.save(out / 'before_after' / f'p{pno:03d}.jpg', quality=85)
        sub = pymupdf.open()
        for pno in PAGES:
            sub.insert_pdf(new, from_page=pno - 1, to_page=pno - 1)
        sub.save(out / 'pilot-pages.pdf', garbage=4, deflate=True)
        for pno, n, t in rows:
            print(f'page {pno}: {n} labels found, {t} translated')


if __name__ == '__main__':
    main(*sys.argv[1:4])
