"""Language profiles: everything the tool needs for one source language.

Only Lao is tested. Other languages work through a profile file (see docs/language-profiles.md)
and are experimental until they pass a self-test.
"""
import json
import re
import unicodedata
from pathlib import Path

PROFILES = {
    'lo': {
        'code': 'lo',
        'name': 'Lao',
        'tested': True,
        'ranges': [[0x0E80, 0x0EFF]],
        'digits': '໐໑໒໓໔໕໖໗໘໙',
        # Main reading: the script model plus English, for Latin words and numbers. Second reading: the language model.
        'tesseract_main': 'script/Lao+eng',
        'tesseract_second': 'lao',
        'install': {'brew': 'tesseract tesseract-lang',
                    'apt': 'tesseract-ocr tesseract-ocr-lao tesseract-ocr-script-laoo'},
        # Old and new spellings of the same letters: ໍາ = ຳ, ຫມ = ໝ, ຫນ = ໜ
        'normalize': [['ໍາ', 'ຳ'], ['ຫມ', 'ໝ'], ['ຫນ', 'ໜ']],
        'dictionary': 'laonlp',
        # Words that do not start or end a term: and, or, of, in, that, to, is, with, from, by, for, according to
        'stopwords': ['ແລະ', 'ຫຼື', 'ຂອງ', 'ໃນ', 'ທີ່', 'ທີ', 'ໃຫ້', 'ເປັນ', 'ມີ', 'ແມ່ນ', 'ກັບ', 'ຈາກ', 'ໂດຍ', 'ເພື່ອ', 'ຕາມ', 'ດັ່ງນີ້'],
        # A section starts at "Article N"; batches end only at section starts.
        'section_heading': r'^\s*ມາດຕາ\s*(\d+)',
        'definitions_heading': r'ອະທິບາຍຄ[ຳໍ]າ?ສັບ',
        # Tone marks and vowels stack above and below the line, outside the word boxes OCR reports.
        'stacked_marks': True,
        'combining_marks': '\u0eb1\u0eb4-\u0ebc\u0ec8-\u0ecd',
        # Conventions for reading labels in pictures (maps above all)
        'picture_notes': ('On Lao maps, ມ. is a district (ເມືອງ): write "Name District"; ຂ. is a province (ແຂວງ): '
                          '"Name Province". Countries: ຈີນ China, ໄທ Thailand, ຫວຽດນາມ Vietnam, ມຽນມາ Myanmar, '
                          'ກຳປູເຈຍ Cambodia. Use the usual English spellings of Lao places (Phongsaly, Luang Prabang, '
                          'Savannakhet, Champasak, Vientiane).'),
    },
}


def load(code_or_path):
    """A built-in profile by code ('lo'), or a JSON profile file."""
    if code_or_path in PROFILES:
        return Profile(PROFILES[code_or_path])
    path = Path(code_or_path)
    if path.exists():
        return Profile(json.loads(path.read_text()))
    raise SystemExit(f'No language profile "{code_or_path}". Built in: {", ".join(PROFILES)}; '
                     'or pass a profile file (docs/language-profiles.md).')


class Profile(dict):
    def __getattr__(self, k):
        return self[k]

    def in_script(self, ch):
        return any(lo <= ord(ch) <= hi for lo, hi in self['ranges'])

    def count(self, text):
        return sum(self.in_script(c) for c in text)

    def norm(self, text):
        text = unicodedata.normalize('NFC', text)
        marks = self.get('combining_marks')
        if marks:       # PDFs from word processors often put a space before a vowel or tone mark
            text = re.sub(f' +(?=[{marks}])', '', text)
        for a, b in self.get('normalize', []):
            text = text.replace(a, b)
        return text

    def ascii_digits(self, text):
        digits = self.get('digits') or ''
        return text.translate({ord(d): str(i) for i, d in enumerate(digits)}) if digits else text

    def section(self, text):
        pat = self.get('section_heading')
        m = re.match(pat, self.norm(text)) if pat else None
        return int(m.group(1)) if m and m.groups() else (True if m else None)
