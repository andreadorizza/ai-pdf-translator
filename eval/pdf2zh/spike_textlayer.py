"""Spike: can PDFMathTranslate take our Lao text layer and our translations, with no change to its code?

1. Make a searchable PDF of decree pages 9-10: the scan plus Tesseract's invisible text (script/Lao+eng),
   standing in for the checked text our tool would write.
2. Pass 1: run pdf2zh's OCR-page path on it with a translator that only records each paragraph.
3. Pass 2: run it again with a translator that returns English from our pilot (run2), matched by Lao text.
Patches (no fork): pdf2zh.high_level._ocr_pages marks pages that have an image and a text layer as OCR pages
(the upstream change we would propose), and pdf2zh.converter.GoogleTranslator is replaced by our class.
"""
import difflib, json, subprocess, sys, tempfile
from pathlib import Path
import fitz
import pdf2zh.converter as conv
import pdf2zh.high_level as hl
from pdf2zh.translator import BaseTranslator
from pdf2zh.doclayout import OnnxModel

MODEL = OnnxModel.load_available()

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
SRC = ROOT / 'pages/Decree-on-Carbon-Credits_PM-Signed_Lao-and-Eng-1.pdf'
PAGES = [9, 10]
TESS = '/opt/homebrew/share/tessdata'

# 1. searchable PDF
out = fitz.open()
with tempfile.TemporaryDirectory() as tmp:
    for n in PAGES:
        png = f'{tmp}/p{n}.png'
        fitz.open(SRC)[n - 1].get_pixmap(dpi=300).save(png)
        subprocess.run(['tesseract', png, f'{tmp}/p{n}', '--tessdata-dir', TESS, '-l', 'script/Lao+eng', 'pdf'],
                       check=True, capture_output=True)
        out.insert_pdf(fitz.open(f'{tmp}/p{n}.pdf'))
src_pdf = HERE / 'spike_input.pdf'
out.save(src_pdf)


def ocr_pages_from_layer(doc, pages, lang_in, cancel):
    return {i for i, p in enumerate(doc) if p.get_text().strip() and p.get_image_info()}


hl._ocr_pages = ocr_pages_from_layer


class Agent(BaseTranslator):
    name = 'google'
    lookup = None
    seen = []

    def __init__(self, lang_in, lang_out, model, envs=None, prompt=None, ignore_cache=False, **kw):
        super().__init__(lang_in, lang_out, model, True)

    def translate(self, text, ignore_cache=False):
        Agent.seen.append(text)
        return Agent.lookup(text) if Agent.lookup else '[recorded]'


conv.GoogleTranslator = Agent


def run(tag):
    Agent.seen = []
    try:
        hl.translate(files=[str(src_pdf)], output=str(HERE / tag), lang_in='lo', lang_out='en', service='google', thread=1, model=MODEL)
    except ValueError as e:  # the font-subsetting crash seen in the full runs
        print('subset crash:', e, '- retrying with skip_subset_fonts')
        hl.translate(files=[str(src_pdf)], output=str(HERE / tag), lang_in='lo', lang_out='en', service='google',
                     thread=1, skip_subset_fonts=True, model=MODEL)
    return list(Agent.seen)


# 2. pass 1
Path(HERE / 'spike1').mkdir(exist_ok=True)
paras = run('spike1')
print(f'pass 1: {len(paras)} paragraphs')
for p in paras[:6]: print('  ', p[:90].replace('\n', ' '))

# 3. pass 2, English from our pilot matched by Lao text
blocks = [b for b in json.load(open(ROOT / 'pilot/run2/blocks.json')) if b['page'] in PAGES]
tr = json.load(open(ROOT / 'pilot/run2/translation.json'))
en = {}
for c in tr['chunks']: en.update(c.get('translations', {}))
norm = lambda s: ''.join(s.split())


def lookup(text):
    t = norm(text)
    hits = [(difflib.SequenceMatcher(None, t, norm(b['text']), autojunk=False).ratio(), b) for b in blocks]
    score, b = max(hits, key=lambda h: h[0])
    lookup.scores.append(round(score, 2))
    return en.get(b['id'], '[missing]') if score > 0.5 else '[no match]'


lookup.scores = []
Agent.lookup = lookup
Path(HERE / 'spike2').mkdir(exist_ok=True)
run('spike2')
print(f'pass 2: our blocks on these pages {len(blocks)}, pdf2zh paragraphs {len(paras)}, match ratios {sorted(lookup.scores)}')
mono = next((HERE / 'spike2').glob('*-mono.pdf'))
d = fitz.open(mono)
for i, p in enumerate(d): p.get_pixmap(dpi=80).save(HERE / f'spike2_page{PAGES[i]}.png')
print('output', mono, round(mono.stat().st_size / 1e6, 1), 'MB')
