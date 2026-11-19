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
from pymupdf import Point, Rect

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


def _merged_words(page, prof):
    """Words of a text page. PDFs from word processors tag runs with ActualText: PyMuPDF uses it, which gives
    correct Lao but can drop figures, brackets and Latin words the page shows. Add those back from the raw glyphs."""
    words = page.get_text('words')
    covered = [Rect(w[:4]) for w in words]
    raw = page.get_text('rawdict', flags=pymupdf.TEXTFLAGS_RAWDICT | pymupdf.TEXT_IGNORE_ACTUALTEXT)
    extra = []
    for b in raw['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                run, box = '', None
                for c in s['chars'] + [None]:
                    keep = False
                    if c is not None and c['c'].strip() and not (prof and prof.in_script(c['c'])):
                        r = Rect(c['bbox'])
                        centre = (r.tl + r.br) / 2
                        keep = not any(centre in w for w in covered)
                    if keep:
                        run += c['c']
                        box = Rect(c['bbox']) if box is None else box | Rect(c['bbox'])
                    elif run:
                        same_line = [w for w in words if w[1] < box.y1 and w[3] > box.y0]
                        dup = any(run in w[4] and abs(w[0] - box.x0) < 40 for w in same_line)
                        if not dup:     # some PDFs draw a figure twice, once inside the ActualText word
                            near = min(same_line or words, key=lambda w: abs((w[1] + w[3]) / 2 - (box.y0 + box.y1) / 2),
                                       default=None)
                            extra.append((*box, run, near[5] if near else -1, near[6] if near else -1, -1))
                        run, box = '', None
    return words + extra


class _PageWithFigures:
    """A page whose words include what ActualText hides (see _merged_words); everything else is the page."""

    def __init__(self, page, prof):
        self._page, self._prof = page, prof

    def __getattr__(self, name):
        return getattr(self._page, name)

    def get_text(self, kind='text', *args, **kwargs):
        if kind == 'words' and not args and not kwargs:
            return _merged_words(self._page, self._prof)
        return self._page.get_text(kind, *args, **kwargs)


def _ocr_page(page, detection, translator, font, thread, cancellation_event=None):
    pno = page.number + 1
    is_scan = pno in STATE['scan_pages']
    source = page if is_scan else _PageWithFigures(page, STATE['profile'])
    paras = zocr.ocr_paragraphs(source, detection)
    extras = _labels(page, source, paras, is_scan)
    if STATE['mode'] == 'record':
        kind = 'scan' if is_scan else 'text'
        for bounds, text, size, _ in paras:
            STATE['records'].append({'page': pno, 'kind': kind, 'role': 'paragraph', 'text': text,
                                     'bbox': [round(v, 1) for v in bounds], 'size': round(size, 2)})
        for x in extras:
            rec = {'page': pno, 'kind': kind, 'role': x['role'], 'text': x['text'],
                   'bbox': [round(v, 1) for v in x['bbox']], 'size': round(x['size'], 2)}
            rec.update({k: x[k] for k in ('table', 'row', 'col') if k in x})
            STATE['records'].append(rec)
        return
    _write_page(page, detection, paras, extras)


# ---------- text outside paragraphs: table cells, labels in figures, running headers, covers ----------

def _spans(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['text'].strip():
                    out.append((Rect(s['bbox']), s['size'], s['color']))
    return out


def _lines(words):
    """Words grouped into lines (top to bottom), each line left to right."""
    lines = []
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        h = max(w[3] - w[1], 1)
        if lines and abs((w[1] + w[3]) / 2 - lines[-1][0]) < 0.5 * h:
            lines[-1][1].append(w)
        else:
            lines.append([(w[1] + w[3]) / 2, [w]])
    return [sorted(l, key=lambda w: w[0]) for _, l in lines]


def _join(words):
    return ' '.join(' '.join(w[4] for w in line) for line in _lines(words))


def _bbox(words):
    r = Rect(words[0][:4])
    for w in words[1:]:
        r |= Rect(w[:4])
    return r


def _labels(page, source, paras, is_scan):
    """Text the paragraph finder leaves out: cells of ruled tables (digital pages), then clusters of the remaining
    words, such as labels in figures, running headers and footers, and cover titles. Only text in the source script."""
    prof = STATE['profile']
    rot = page.rotation_matrix
    used = {tuple(round(v, 1) for v in r) for *_, rects in paras for r in rects}
    words = []
    for w in source.get_text('words'):
        r = Rect(w[:4]) * rot
        if w[4].strip() and tuple(round(v, 1) for v in r) not in used:
            words.append((r.x0, r.y0, r.x1, r.y1, w[4]))
    if not words:
        return []
    spans = [] if is_scan else _spans(page)
    page_mid = (page.rect.x0 + page.rect.x1) / 2
    items = []

    def add(ws, role, frame=None, **meta):
        text = _join(ws)
        if prof is None or prof.count(text) < 2:
            return
        box = _bbox(ws)
        near = [(s, c) for r, s, c in spans if (r & box).get_area() > 0]
        size = sorted(s for s, _ in near)[len(near) // 2] if near else 0.72 * sorted(w[3] - w[1] for w in ws)[len(ws) // 2]
        colors = [c for _, c in near]
        color = max(set(colors), key=colors.count) if colors else 0
        frame = frame or box
        centred = abs((box.x0 + box.x1) / 2 - (frame.x0 + frame.x1) / 2) < 0.12 * frame.width if role == 'cell' \
            else abs((box.x0 + box.x1) / 2 - page_mid) < 0.05 * page.rect.width
        items.append(dict(meta, role=role, text=text, bbox=box, frame=frame, size=size, color=color,
                          align='center' if centred else 'left', words=[Rect(w[:4]) for w in ws]))

    if not is_scan:
        try:
            tables = page.find_tables().tables
        except Exception:          # table detection is a bonus; a page it cannot read keeps its tables as they are
            tables = []
        for ti, tab in enumerate(tables):
            for ri, row in enumerate(tab.rows):
                for ci, cell in enumerate(row.cells):
                    if cell is None:
                        continue
                    cr = Rect(cell)
                    inside = [w for w in words if Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) in cr]
                    if inside:
                        words = [w for w in words if w not in inside]
                        add(inside, 'cell', frame=cr + (1.5, 1.5, -1.5, -1.5), table=ti, row=ri, col=ci)

    chunks = []                     # each line split where the gap between words is wide
    for line in _lines(words):
        cur = [line[0]]
        for w in line[1:]:
            h = max(w[3] - w[1], 1)
            if w[0] - cur[-1][2] > 1.0 * h:
                chunks.append(cur)
                cur = []
            cur.append(w)
        chunks.append(cur)
    clusters = []                   # stack chunks that sit in one column with a line's gap between them
    for ch in sorted(chunks, key=lambda c: _bbox(c).y0):
        b = _bbox(ch)
        for cl in clusters:
            a = _bbox(cl)
            overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
            if 0 <= b.y0 - a.y1 < 0.6 * a.height / max(1, len(_lines(cl))) + 2 and overlap > 0.5 * min(a.width, b.width):
                cl.extend(ch)
                break
        else:
            clusters.append(list(ch))
    for cl in clusters:
        add(cl, 'label')
    return items


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


def _write_page(page, detection, paras, extras):
    pno = page.number + 1
    prof = STATE['profile']
    is_scan = pno in STATE['scan_pages']
    items = []
    for bounds, text, size, words in paras:
        en = STATE['lookup'].get((pno, key(text)))
        if en is None:
            STATE['missing'].append((pno, text))
            continue
        items.append([Rect(bounds), en, size, words, text])
    labels = []
    for x in extras:
        en = STATE['lookup'].get((pno, key(x['text'])))
        if en is None:
            STATE['missing'].append((pno, x['text']))
        else:
            labels.append(dict(x, english=en))
    if not items and not labels:
        return
    scan_boxes = _scan_word_boxes(pno, page)
    pad = 0.3 if prof and prof.get('stacked_marks') else 0.1
    if items:
        # The text layer gives short lines (headings, list items) a small size: no paragraph goes below body text.
        long_sizes = sorted(it[2] for it in items if len(it[4]) > 60) or sorted(it[2] for it in items)
        body = long_sizes[len(long_sizes) // 2]
        for it in items:
            it[2] = min(max(it[2], body), 12)
        wide = [b for b, *_ in items if b.width > page.rect.width * 0.4]
        left = min((b.x0 for b in wide), default=min(b.x0 for b, *_ in items))
        right = max((b.x1 for b in wide), default=max(b.x1 for b, *_ in items))
        for it in items:      # the scan's word boxes are taller than the text layer's: use them for the box height
            inside = [r for r in scan_boxes if (r.tl + r.br) / 2 in it[0]]
            for r in inside:
                it[0] |= Rect(it[0].x0, r.y0 - pad * r.height, it[0].x1, r.y1 + pad * r.height)
    titles = [Rect(*b.xyxy) for b in detection.boxes if detection.names[int(b.cls)] == 'title']
    source_areas = [(Rect(b), s, w) for b, en, s, w, src in items] + [(x['bbox'], x['size'], x['words']) for x in labels]
    ordered = sorted(items, key=lambda it: it[0].y0)
    with pymupdf.open() as overlay:
        target = overlay.new_page(width=page.rect.width, height=page.rect.height)
        if is_scan:             # cover first, then write, so no box hides English
            for bounds, _, words in source_areas:
                for r in words:
                    target.draw_rect(r + (-0.5, -0.5, 0.5, 0.5), color=None, fill=(1, 1, 1))
                for r in scan_boxes:
                    if (r.tl + r.br) / 2 in bounds:
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
        for x in labels:        # cells, figure labels, headers: in their own frame, size and colour
            box = Rect(x['frame'])
            if x['role'] != 'cell':
                box = Rect(box.x0 - 2, box.y0, box.x1 + 2, max(box.y1, box.y0 + x['size'] * 1.3))
            color = '#000000' if is_scan else f"#{x['color']:06x}"
            css = (f"* {{font-family: serif; font-size: {x['size']:.1f}pt; line-height: 1.1; margin: 0; padding: 0;"
                   f" color: {color}}} p {{text-align: {x['align']}}}")
            target.insert_htmlbox(box, f"<p>{escape(x['english'])}</p>", css=css, scale_low=0)
        links = page.get_links()
        if is_scan:
            page.add_redact_annot(page.rect * page.derotation_matrix, fill=False)   # our invisible text layer
        else:       # a text page: remove the translated text only; untranslated text and drawings stay
            for bounds, size, words in source_areas:
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
