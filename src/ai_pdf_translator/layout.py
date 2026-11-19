"""Layout and write-back through PDFMathTranslate (pdf2zh), pinned to one commit, with runtime patches:

1. Every page we translate goes through pdf2zh's OCR-page path, which reads words with PyMuPDF; pdf2zh does no OCR
   of its own. Its text-page path counts combining marks (Lao, Thai, Khmer vowels and tones) as formula characters
   and replaces them with placeholders, so we do not use it.
2. Translations come from our files: a translator class records each paragraph (pass 1) or returns
   the English we have for it (pass 2). It takes the place of the "google" service and makes no network calls.
3. Scan pages are written by our code: white boxes cover the scan's own word boxes (with room for stacked
   marks), headings may use the full column, and the English uses a built-in font, which keeps the file small.

The patches are temporary: docs/adr/0003 lists what we will offer upstream so they can go.
"""
import re
import shutil
import tempfile
from html import escape
from pathlib import Path

import pymupdf
from pymupdf import Rect

import pdf2zh.converter as conv
import pdf2zh.high_level as hl
import pdf2zh.ocr as zocr
from pdf2zh.translator import BaseTranslator

from .ocr import DPI, tesseract_words

STATE = {'mode': 'record', 'scan_pages': set(), 'pages': set(), 'records': [], 'lookup': {}, 'page': None,
         'profile': None, 'work': None, 'missing': []}
_MODEL = None


def key(text):
    return ''.join(text.split())


class AgentTranslator(BaseTranslator):
    name = 'google'

    def __init__(self, lang_in, lang_out, model, envs=None, prompt=None, ignore_cache=False, **kw):
        super().__init__(lang_in, lang_out, model, True)
        self.no_cache = True

    def translate(self, text, ignore_cache=False):
        page = STATE['page']
        if STATE['mode'] == 'record':
            STATE['records'].append({'page': page, 'kind': 'text', 'text': text})
            return text
        en = STATE['lookup'].get((page, key(text)))
        if en is None:
            STATE['missing'].append((page, text))
            return text
        return en


def _scan_pages(doc, pages, lang_in, cancellation_event):
    return {p - 1 for p in STATE['pages'] if not pages or (p - 1) in pages}


_receive_layout = conv.TranslateConverter.receive_layout


def _receive_layout_with_page(self, ltpage):
    STATE['page'] = ltpage.pageid + 1
    return _receive_layout(self, ltpage)


def _ocr_page(page, detection, translator, font, thread, cancellation_event=None):
    pno = page.number + 1
    paras = zocr.ocr_paragraphs(page, detection)
    if not paras:
        return
    if STATE['mode'] == 'record':
        for bounds, text, size, _ in paras:
            STATE['records'].append({'page': pno, 'kind': 'scan' if pno in STATE['scan_pages'] else 'text', 'text': text,
                                     'bbox': [round(v, 1) for v in bounds], 'size': round(size, 2)})
        return
    _write_scan_page(page, detection, paras)


def patch():
    hl._ocr_pages = _scan_pages
    conv.GoogleTranslator = AgentTranslator
    conv.TranslateConverter.receive_layout = _receive_layout_with_page
    zocr.translate_ocr_page = _ocr_page


# ---------- writing a scan page ----------

TITLE = re.compile(r'^((?:Article|Chapter|Section|Part)\s+[\dIVXLC]+[:.]?\s+[^.:;<\n]{0,120}[.:]?)(\s*)(.*)$', re.S)


def _scan_word_boxes(pno, page):
    """The scan's own word boxes (main reading), in page points; they include more of each glyph than the text layer."""
    tsv = Path(STATE['work']) / 'ocr' / f'p{pno:03d}.main.tsv'
    if not tsv.exists():
        return []
    s = 72 / DPI
    return [Rect(*(v * s for v in w['box'])) * page.derotation_matrix for w in tesseract_words(tsv)]


def _write_scan_page(page, detection, paras):
    pno = page.number + 1
    prof = STATE['profile']
    items = []
    for bounds, text, size, words in paras:
        en = STATE['lookup'].get((pno, key(text)))
        if en is None:
            STATE['missing'].append((pno, text))
            continue
        items.append([Rect(bounds), en, size, words, text])
    if not items:
        return
    # The text layer gives short lines (headings, list items) a small size: no paragraph goes below body text.
    long_sizes = sorted(it[2] for it in items if len(it[4]) > 60) or sorted(it[2] for it in items)
    body = long_sizes[len(long_sizes) // 2]
    for it in items:
        it[2] = min(max(it[2], body), 12)
    titles = [Rect(*b.xyxy) for b in detection.boxes if detection.names[int(b.cls)] == 'title']
    wide = [b for b, *_ in items if b.width > page.rect.width * 0.4]
    left = min((b.x0 for b in wide), default=min(b.x0 for b, *_ in items))
    right = max((b.x1 for b in wide), default=max(b.x1 for b, *_ in items))
    scan_boxes = _scan_word_boxes(pno, page)
    pad = 0.3 if prof and prof.get('stacked_marks') else 0.1
    for it in items:      # the scan's word boxes are taller than the text layer's: use them for the box height
        inside = [r for r in scan_boxes if (r.tl + r.br) / 2 in it[0]]
        for r in inside:
            it[0] |= Rect(it[0].x0, r.y0 - pad * r.height, it[0].x1, r.y1 + pad * r.height)
    source_areas = [(Rect(b), en, s, w, src) for b, en, s, w, src in items]
    ordered = sorted(items, key=lambda it: it[0].y0)
    with pymupdf.open() as overlay:
        target = overlay.new_page(width=page.rect.width, height=page.rect.height)
        for bounds, _, _, words, _ in items:      # cover first, then write, so no box hides English
            if pno not in STATE['scan_pages']:
                continue                          # vector text is removed instead of covered
            for r in words:
                target.draw_rect(r + (-0.5, -0.5, 0.5, 0.5), color=None, fill=(1, 1, 1))
            for r in scan_boxes:
                c = (r.tl + r.br) / 2
                if c in bounds:
                    target.draw_rect(Rect(r.x0 - 1, r.y0 - pad * r.height, r.x1 + 1, r.y1 + pad * r.height),
                                     color=None, fill=(1, 1, 1))
        for i, (bounds, en, size, _, _) in enumerate(ordered):
            centered = (any((t & bounds).get_area() > bounds.get_area() / 2 for t in titles)
                        or (abs((bounds.x0 + bounds.x1) / 2 - (left + right) / 2) < 20 and bounds.width < 0.7 * (right - left)))
            box = Rect(bounds)
            if centered:            # a centered caption or title may use the whole column, still centered
                box.x0, box.x1 = min(box.x0, left), max(box.x1, right)
            else:
                box.x1 = max(box.x1, right)
            below = [o[0].y0 for o in ordered[i + 1:] if o[0].y0 > bounds.y0 + 2 and o[0].x0 < box.x1 and o[0].x1 > box.x0]
            limit = min(below) - 1 if below else min(page.rect.y1 - 40, bounds.y1 + 3 * size)
            box.y1 = max(box.y1, limit, min(limit, box.y0 + size * 1.35))
            body = escape(en).replace('\n', '<br>')
            m = TITLE.match(body)
            if m and len(m.group(1)) < 140:
                body = f'<b>{m.group(1)}</b>' + (f'<br>{m.group(3)}' if m.group(3) else '')
            css = (f'* {{font-family: serif; font-size: {size:.1f}pt; line-height: 1.2; margin: 0; padding: 0}}'
                   f' p {{text-align: {"center" if centered else "left"}}}')
            target.insert_htmlbox(box, f'<p>{body}</p>', css=css, scale_low=0)
        links = page.get_links()
        if pno in STATE['scan_pages']:
            page.add_redact_annot(page.rect * page.derotation_matrix, fill=False)   # our invisible text layer
        else:       # a text page: remove the text in each translated paragraph only; tables, labels, headers stay
            for bounds, _, size, words, _ in source_areas:
                area = Rect(bounds)
                for r in words:
                    area |= r
                # Glyph boxes in Lao fonts are tall, and any glyph touching the area is removed: shrink the area
                # vertically so the lines above and below (a running header, the next paragraph) are not touched.
                area = Rect(area.x0 - 1, area.y0 + 0.25 * size, area.x1 + 2, area.y1 - 0.25 * size)
                page.add_redact_annot(area * page.derotation_matrix, fill=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        for link in links:
            page.insert_link(link)
        page.show_pdf_page(page.rect * page.derotation_matrix, overlay, 0, rotate=page.rotation)


# ---------- running pdf2zh ----------

def _model():
    global _MODEL
    if _MODEL is None:
        from pdf2zh.doclayout import OnnxModel, set_backend
        set_backend('cpu')      # Apple's CoreML backend fails on pages of a different size; the CPU handles any page
        _MODEL = OnnxModel.load_available()
    return _MODEL


def _translate(pdf, pages, lang_in, outdir, threads):
    kwargs = dict(files=[str(pdf)], output=str(outdir), pages=[p - 1 for p in pages], lang_in=lang_in,
                  lang_out='en', service='google', thread=threads, model=_model())
    try:
        hl.translate(**kwargs)
    except ValueError as e:          # pdf2zh's font subsetting can fail (upstream issue #975)
        if 'bad' not in str(e):
            raise
        hl.translate(**kwargs, skip_subset_fonts=True)


def record(pdf, pages, scan_pages, prof, work, threads=4):
    """Pass 1: the paragraphs pdf2zh finds, in reading order, with page and box (scan pages)."""
    patch()
    STATE.update(mode='record', records=[], scan_pages=set(scan_pages), pages=set(pages), profile=prof, work=str(work))
    with tempfile.TemporaryDirectory() as tmp:
        _translate(pdf, pages, prof.code, tmp, threads)
    return list(STATE['records'])


def render(pdf, pages, scan_pages, prof, work, lookup, out_mono, out_dual, threads=4):
    """Pass 2: write the English we have for each paragraph. Returns paragraphs that had no English."""
    patch()
    STATE.update(mode='render', lookup=lookup, missing=[], scan_pages=set(scan_pages), pages=set(pages), profile=prof,
                 work=str(work))
    with tempfile.TemporaryDirectory() as tmp:
        _translate(pdf, pages, prof.code, tmp, threads)
        stem = Path(pdf).stem
        for src, dst in ((f'{stem}-mono.pdf', out_mono), (f'{stem}-dual.pdf', out_dual)):
            doc = pymupdf.open(Path(tmp) / src)
            doc.save(dst, garbage=4, deflate=True)
    return list(STATE['missing'])
