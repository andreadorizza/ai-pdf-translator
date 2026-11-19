"""Page kinds, the two OCR readings, and the PDF with our text layer on its scan pages."""
import csv
import io
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf

DPI = 300


def page_kinds(doc, prof):
    """text: usable text layer in the source script. scan: image only, or a text layer without the source script
    (a broken font). target: already in English. blank: nothing to translate."""
    kinds = []
    for page in doc:
        text = page.get_text()
        source = prof.count(text)
        latin = sum(c.isascii() and c.isalpha() for c in text)
        if source >= 30:
            kinds.append('text')
        elif latin >= 300 and source < 5:
            kinds.append('target')
        elif page.get_images() or text.strip():
            kinds.append('scan')
        else:
            kinds.append('blank')
    return kinds


def tesseract_words(tsv_path):
    rows = csv.DictReader(io.StringIO(Path(tsv_path).read_text()), delimiter='\t', quoting=csv.QUOTE_NONE)
    out = []
    for r in rows:
        if r['level'] == '5' and r['text'].strip():
            x, y, w, h = (int(r[k]) for k in ('left', 'top', 'width', 'height'))
            out.append({'text': r['text'], 'conf': float(r['conf']), 'box': (x, y, x + w, y + h),
                        'line': (r['block_num'], r['par_num'], r['line_num'])})
    return out


def _run(cmd):
    env = dict(os.environ, OMP_THREAD_LIMIT='1')   # several pages run at once; one thread each
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode:
        raise SystemExit(f'Tesseract failed: {" ".join(cmd)}\n{p.stderr[-800:]}')


def read_pages(pdf, pages, prof, work, psm=4, workers=4):
    """Render each scan page at 300 DPI and read it twice. The main reading also gives an invisible-text PDF page."""
    d = Path(work) / 'ocr'
    d.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)

    def one(pno):
        base = d / f'p{pno:03d}'
        png = base.with_suffix('.png')
        if not png.exists():
            pix = doc[pno - 1].get_pixmap(dpi=DPI)
            pix.set_dpi(DPI, DPI)
            pix.save(png)
        if not Path(f'{base}.main.tsv').exists():
            _run(['tesseract', str(png), f'{base}.main', '-l', prof.tesseract_main, '--psm', str(psm),
                  '-c', 'textonly_pdf=1', 'pdf', 'tsv'])
        if prof.get('tesseract_second') and not Path(f'{base}.second.tsv').exists():
            _run(['tesseract', str(png), f'{base}.second', '-l', prof.tesseract_second, '--psm', str(psm), 'tsv'])
        return pno

    with ThreadPoolExecutor(workers) as ex:
        for pno in ex.map(one, pages):
            print(f'  OCR page {pno}', flush=True)


def scanned_target_pages(pages, prof, work):
    """Scan pages whose main reading is mostly English are already in the target language."""
    out = set()
    for pno in pages:
        words = tesseract_words(Path(work) / 'ocr' / f'p{pno:03d}.main.tsv')
        text = ''.join(w['text'] for w in words)
        latin = sum(c.isascii() and c.isalpha() for c in text)
        if latin > 200 and prof.count(text) < 0.05 * max(1, latin):
            out.add(pno)
    return out


def searchable_pdf(pdf, scan_pages, work, out):
    """Copy of the source with our main reading as invisible text on each scan page.
    A page whose text layer is broken is first replaced by its image, so the broken text cannot be read."""
    doc = pymupdf.open(pdf)
    d = Path(work) / 'ocr'
    for pno in scan_pages:
        page = doc[pno - 1]
        if page.get_text().strip():
            pix = pymupdf.Pixmap(str(d / f'p{pno:03d}.png'))
            jpg = pix.tobytes('jpeg', jpg_quality=85)
            xref = doc.get_new_xref()
            doc.update_object(xref, '<<>>')
            doc.update_stream(xref, b'')
            page.set_contents(xref)
            page.insert_image(page.rect * page.derotation_matrix, stream=jpg, rotate=page.rotation)
        layer = pymupdf.open(d / f'p{pno:03d}.main.pdf')
        page.show_pdf_page(page.rect * page.derotation_matrix, layer, 0, rotate=page.rotation, overlay=True)
    doc.save(out, garbage=3, deflate=True)
