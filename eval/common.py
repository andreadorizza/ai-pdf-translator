import re
HEADING = re.compile(r'^\s*ມາດຕາ\s*(\d+)')
SKIP = re.compile(r'^\s*(ໝວດທີ|ພາກທີ|ໝວດ\s*\d)|^\s*\d{1,3}\s*$')   # chapter headings, page numbers

def by_article(blocks):
    """Attach each OCR block to the article it belongs to. Chapter headings and page numbers get None."""
    cur, out = 0, []
    for b in blocks:
        m = HEADING.match(b['text'])
        if m: cur = int(m.group(1))
        out.append((None if SKIP.match(b['text']) else cur, b))
    return out
