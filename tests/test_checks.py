from ai_pdf_translator import langs
from ai_pdf_translator.check import number_problems
from ai_pdf_translator.cli import parse_pages
from ai_pdf_translator.plan import batches, number_paragraphs

LO = langs.load('lo')


def test_numbers_found_as_digits_words_and_months():
    src = 'ສະບັບເລກທີ 292/ລບ, ລົງວັນທີ 28/05/2025 ພາຍໃນ 180 ວັນ ແລະ 15 ວັນ'
    en = 'Decree No. 292/GO, dated 28 May 2025, within one hundred and eighty days and fifteen days'
    assert number_problems(src, en, LO) == ['180']          # "one hundred and eighty" is not matched; a person checks
    assert number_problems(src, en.replace('one hundred and eighty', '180'), LO) == []


def test_lao_digits_and_missing_figure():
    assert number_problems('ມາດຕາ ໒໕ ແລະ 3.000 ໂຕນ', 'Article 25 and 300 tonnes', LO) == ['3000']


def test_list_number_at_start_is_ignored():
    assert number_problems('3. ກົດໝາຍ', 'Law', LO) == []


def test_parse_pages():
    assert parse_pages('2,5-7', 10) == [2, 5, 6, 7]
    assert parse_pages(None, 3) == [1, 2, 3]
    assert parse_pages('9-12', 10) == [9, 10]


def test_batches_end_at_sections_only():
    recs = []
    for art in range(1, 7):
        recs.append({'page': art, 'kind': 'scan', 'text': f'ມາດຕາ {art} ຫົວຂໍ້'})
        recs.append({'page': art, 'kind': 'scan', 'text': 'ກ' * 2000})
    paras = number_paragraphs(recs, LO)
    groups = batches(paras, LO)
    assert all(LO.section(g[0]['text']) is not None for g in groups)
    assert sum(len(g) for g in groups) == len(paras)
    assert paras[1]['section'] == 1 and paras[-1]['section'] == 6


def test_figures_inside_latin_words_are_skipped():
    assert number_problems('ກາກບອນໄດອອກໄຊ (C0), (N20) ແລະ 25 ໂຕນ', 'carbon dioxide (CO2), (N2O) and 25 tonnes', LO) == []
