"""Text inside pictures, the way Google Lens does it: find every label, read and translate it from zoomed crops,
erase it from the picture's pixels, and draw the English in its place, colour and size.

  find       a text detector built for images (PaddleOCR's, through RapidOCR) on overlapping tiles of the picture
             at twice its size, joined with Tesseract's sparse-mode words; boxes on one line close together merge
  read       labels cropped, zoomed and laid out on numbered contact sheets that a vision subagent reads
  redraw     OpenCV inpainting rebuilds the background under each label; Pillow draws the English
"""
import io
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

from .ocr import tesseract_words

TILE, OVERLAP = 960, 160


def pictures_on(doc, pno, min_side=150):
    """The pictures on a page, at their own resolution, with where they sit on the page."""
    page = doc[pno - 1]
    out = []
    for info in page.get_images(full=True):
        xref = info[0]
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        img = Image.open(io.BytesIO(doc.extract_image(xref)['image'])).convert('RGB')
        if min(img.size) < min_side:
            continue
        out.append({'xref': xref, 'rect': rects[0], 'image': img})
    return out


def _detector():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(det_limit_side_len=1024, det_limit_type='max', det_thresh=0.2, det_box_thresh=0.3,
                    det_unclip_ratio=1.8)


def _rapid_boxes(big, det):
    a = np.array(big)
    boxes = []
    for y in range(0, big.height, TILE - OVERLAP):
        for x in range(0, big.width, TILE - OVERLAP):
            tile = a[y:y + TILE, x:x + TILE]
            if tile.shape[0] < 40 or tile.shape[1] < 40:
                continue
            found, _ = det(tile, use_det=True, use_cls=False, use_rec=False)
            for q in found or []:
                xs, ys = [p[0] + x for p in q], [p[1] + y for p in q]
                boxes.append([min(xs), min(ys), max(xs), max(ys)])
    return boxes


def _tesseract_boxes(big, prof):
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / 'p.png'
        big.save(png)
        subprocess.run(['tesseract', str(png), str(Path(tmp) / 'p'), '-l', prof.tesseract_main, '--psm', '11', 'tsv'],
                       capture_output=True, check=True)
        words = tesseract_words(Path(tmp) / 'p.tsv')
    return [list(w['box']) for w in words if w['conf'] >= 20 and prof.count(w['text']) >= 1]


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _inter(a, b):
    return _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def find_labels(img, prof, det=None):
    """Label boxes in the picture's own pixels."""
    det = det or _detector()
    boxes = []
    for scale in (2, 3):            # a second, larger pass finds the small labels of dense maps
        big = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
        boxes += [[v / scale for v in b] for b in _rapid_boxes(big, det)]
        if scale == 2:
            boxes += [[v / scale for v in b] for b in _tesseract_boxes(big, prof)]
    boxes = [b for b in boxes if b[3] - b[1] >= 4 and b[2] - b[0] >= 3]
    merged = []                     # one box per piece of text: overlapping boxes join
    for b in sorted(boxes, key=lambda b: -_area(b)):
        for m in merged:
            if _inter(b, m) > 0.3 * min(_area(b), _area(m)):
                m[:] = [min(m[0], b[0]), min(m[1], b[1]), max(m[2], b[2]), max(m[3], b[3])]
                break
        else:
            merged.append(list(b))
    labels = merged                 # pieces on one line with a small gap form one label ("ມ." and the name)
    changed = True
    while changed:
        changed, out = False, []
        for b in sorted(labels, key=lambda b: (b[1], b[0])):
            h = b[3] - b[1]
            for l in out:
                same_line = min(l[3], b[3]) - max(l[1], b[1]) > 0.5 * min(h, l[3] - l[1])
                gap = max(b[0] - l[2], l[0] - b[2])
                if same_line and gap < 1.1 * min(h, l[3] - l[1]):
                    l[:] = [min(l[0], b[0]), min(l[1], b[1]), max(l[2], b[2]), max(l[3], b[3])]
                    changed = True
                    break
            else:
                out.append(list(b))
        labels = out
    return labels


def contact_sheets(img, labels, out_dir, prefix, per_sheet=36, row_h=60, width=1100):
    """Crops of every label, zoomed, numbered, on sheets a vision model reads in one look each."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=22)
    sheets, items = [], []
    for start in range(0, len(labels), per_sheet):
        group = labels[start:start + per_sheet]
        sheet = Image.new('RGB', (width, row_h * len(group) + 10), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, b in enumerate(group):
            n = start + i + 1
            pad = 0.25 * (b[3] - b[1])
            crop = img.crop((max(0, b[0] - pad), max(0, b[1] - pad), min(img.width, b[2] + pad), min(img.height, b[3] + pad)))
            k = (row_h - 8) / crop.height
            crop = crop.resize((max(1, int(crop.width * k)), row_h - 8), Image.LANCZOS)
            if crop.width > width - 80:
                crop = crop.resize((width - 80, int(crop.height * (width - 80) / crop.width)), Image.LANCZOS)
            y = 5 + i * row_h
            draw.text((8, y + 14), f'{n}', fill=(200, 0, 0), font=font)
            sheet.paste(crop, (70, y + 4))
            draw.line([(0, y + row_h - 1), (width, y + row_h - 1)], fill=(220, 220, 220))
            items.append({'n': n, 'box': [round(v, 1) for v in b]})
        path = out_dir / f'{prefix}-sheet{len(sheets) + 1}.png'
        sheet.save(path)
        sheets.append(path)
    return sheets, items


def _text_colour(region, mask):
    """The colour of the glyphs: the pixels inside the label furthest from its background."""
    px = region[mask > 0].reshape(-1, 3).astype(float)
    if not len(px):
        return (0, 0, 0)
    border = np.concatenate([region[0], region[-1], region[:, 0], region[:, -1]]).astype(float)
    bg = np.median(border, axis=0)
    d = np.linalg.norm(px - bg, axis=1)
    top = px[d >= np.percentile(d, 85)]
    return tuple(int(v) for v in np.median(top, axis=0))


def _barriers(a):
    """Long vertical dark lines (map frames, legend borders, table rules): English must not cross them."""
    import cv2
    gray = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    dark = (gray < 110).astype(np.uint8)
    k = max(25, a.shape[0] // 25)
    return cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((k, 1), np.uint8))


def _layout(draw, text, font_path, w, h, room):
    """Font size and lines for the English: one line in the label's width or the free room to its right,
    else two lines, else a smaller single line."""
    for size in range(max(7, int(h * 0.62)), max(6, int(h * 0.42)) - 1, -1):
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= room:
            return f, [text]
    words = text.split()
    if len(words) > 1:
        for size in range(max(7, int(h * 0.5)), 6, -1):
            f = ImageFont.truetype(font_path, size)
            best = min(range(1, len(words)), key=lambda i: abs(draw.textlength(' '.join(words[:i]), font=f)
                                                               - draw.textlength(' '.join(words[i:]), font=f)))
            lines = [' '.join(words[:best]), ' '.join(words[best:])]
            if max(draw.textlength(l, font=f) for l in lines) <= room:
                return f, lines
    size = max(6, int(h * 0.62))
    f = ImageFont.truetype(font_path, size)
    while size > 6 and draw.textlength(text, font=f) > room:
        size -= 1
        f = ImageFont.truetype(font_path, size)
    return f, [text]


def redraw(img, labels, results, font_path):
    """Erase the labels from the pixels and draw their English: inpainting rebuilds what lay under the text.
    A label the reader was unsure of still gets its best guess; the review list asks a person to check it."""
    import cv2
    a = np.array(img)
    walls = _barriers(a)
    mask = np.zeros(a.shape[:2], np.uint8)
    todo = []
    for n, b in enumerate(labels, 1):
        r = results.get(str(n)) or {}
        en = (r.get('english') or '').strip()
        if r.get('keep') or not (en or r.get('erase')):
            continue
        x0, y0, x1, y1 = (int(round(v)) for v in b)
        pad = max(2, int(0.15 * (y1 - y0)))
        x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(a.shape[1], x1 + pad), min(a.shape[0], y1 + pad)
        region = a[y0:y1, x0:x1]
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
        ink = (np.abs(gray.astype(int) - int(np.median(border))) > 40).astype(np.uint8)
        colour = _text_colour(region, ink)
        ink = cv2.dilate(ink, np.ones((5, 5), np.uint8))
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], ink * 255)
        todo.append((x0, y0, x1, y1, en, colour))
    a = cv2.inpaint(a, mask, 5, cv2.INPAINT_TELEA)
    out = Image.fromarray(a)
    draw = ImageDraw.Draw(out)
    boxes = [(x0, y0, x1, y1) for x0, y0, x1, y1, *_ in todo]
    for x0, y0, x1, y1, en, colour in todo:
        if not en:
            continue                # a fragment that is only erased (a lone "ມ." next to a translated name)
        w, h = x1 - x0, y1 - y0
        band = walls[y0:y1, x1:]
        cols = np.where(band.any(axis=0))[0]
        right = x1 + (cols[0] - 3 if len(cols) else a.shape[1] - x1 - 2)
        for bx0, by0, bx1, by1 in boxes:   # nor run into the next label on the same line
            if bx0 >= x1 and min(by1, y1) - max(by0, y0) > 0.3 * h:
                right = min(right, bx0 - 3)
        room = max(w, min(right - x0, 2.5 * w))
        f, lines = _layout(draw, en, font_path, w, h, room)
        size = f.size
        light = sum(colour) / 3 > 140
        halo = (0, 0, 0) if light else (255, 255, 255)
        top = y0 + (h - size * 1.1 * len(lines)) / 2
        for i, line in enumerate(lines):
            draw.text((x0, top + i * size * 1.1 - 1), line, font=f, fill=colour, stroke_width=1, stroke_fill=halo)
    return out


def font_path():
    from pdf2zh.high_level import download_remote_fonts
    return download_remote_fonts('en')


# ---------- in the pipeline ----------

def prepare(pdf, pages, prof, work, paragraphs, sheets_per_task=8):
    """Find the labels of every picture on the given pages and write reading tasks (pictures/NNN.json).
    A label under text that is translated anyway (a cover title's shadow) is only erased, not read."""
    work = Path(work)
    d = work / 'pictures'
    (d / 'sheets').mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    det = _detector()
    taken = {}
    for p in paragraphs:
        if p.get('bbox'):
            taken.setdefault(p['page'], []).append(pymupdf.Rect(p['bbox']))
    index, sheet_list = {}, []
    for pno in pages:
        for pic in pictures_on(doc, pno):
            key = f"p{pno:03d}-{pic['xref']}"
            img, r = pic['image'], pic['rect']
            sx, sy = r.width / img.width, r.height / img.height
            read, erase = [], []
            for b in find_labels(img, prof, det):
                pb = pymupdf.Rect(r.x0 + b[0] * sx, r.y0 + b[1] * sy, r.x0 + b[2] * sx, r.y0 + b[3] * sy)
                (erase if any((pb & t).get_area() > 0.3 * pb.get_area() for t in taken.get(pno, [])) else read).append(b)
            if not read and not erase:
                continue
            sheets = contact_sheets(img, read, d / 'sheets', key)[0] if read else []
            index[key] = {'page': pno, 'rect': [r.x0, r.y0, r.x1, r.y1], 'size': list(img.size),
                          'labels': read, 'erase': erase}
            sheet_list += [(key, s) for s in sheets]
    (d / 'index.json').write_text(json.dumps(index))
    for old in d.glob('[0-9][0-9][0-9].json'):
        if not (d / f'{old.stem}.result.json').exists():
            old.unlink()
    tasks = 0
    for i in range(0, len(sheet_list), sheets_per_task):
        tasks += 1
        name = f'{tasks:03d}'
        group = sheet_list[i:i + sheets_per_task]
        (d / f'{name}.json').write_text(json.dumps(
            {'task': name, 'instructions': 'PICTURES.md', 'output': f'pictures/{name}.result.json',
             'sheets': [{'picture': k, 'file': str(s.relative_to(work))} for k, s in group]}, indent=1))
    return len(index), sum(len(v['labels']) for v in index.values()), tasks


def load_results(work):
    out = {}
    for f in sorted((Path(work) / 'pictures').glob('*.result.json')):
        for key, res in json.loads(f.read_text()).items():
            out.setdefault(key, {}).update(res)
    return out


def apply(work, in_pdf, out_pdf):
    """Redraw every picture that has readings, in a copy of the PDF. Returns the labels, for Markdown and review."""
    work = Path(work)
    index = json.loads((work / 'pictures' / 'index.json').read_text())
    results = load_results(work)
    doc = pymupdf.open(in_pdf)
    fp = font_path()
    labels_out = []
    for key, entry in index.items():
        page = doc[entry['page'] - 1]
        want = pymupdf.Rect(entry['rect'])
        xref = None
        for info in page.get_images(full=True):
            rects = page.get_image_rects(info[0])
            if rects and abs(rects[0].x0 - want.x0) < 1 and abs(rects[0].y0 - want.y0) < 1:
                xref = info[0]
                break
        if xref is None:
            continue
        img = Image.open(io.BytesIO(doc.extract_image(xref)['image'])).convert('RGB')
        if list(img.size) != entry['size']:
            continue
        res = dict(results.get(key, {}))
        n = len(entry['labels'])
        for j, _ in enumerate(entry['erase'], n + 1):
            res[str(j)] = {'erase': True}
        out = redraw(img, entry['labels'] + entry['erase'], res, fp)
        buf = io.BytesIO()
        out.save(buf, 'JPEG', quality=90)
        page.replace_image(xref, stream=buf.getvalue())
        for i in range(1, n + 1):
            r = results.get(key, {}).get(str(i)) or {}
            if r.get('keep') or r.get('erase') or not (r.get('english') or '').strip():
                continue
            labels_out.append({'page': entry['page'], 'source': r.get('source', ''), 'english': r['english'],
                               'unsure': bool(r.get('unsure'))})
    doc.save(out_pdf, garbage=3, deflate=True)
    return labels_out
