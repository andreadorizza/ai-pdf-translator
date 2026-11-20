from ai_pdf_translator import langs
from ai_pdf_translator.check import number_problems
from ai_pdf_translator.cli import parse_pages
from ai_pdf_translator.plan import batches, number_paragraphs

LO = langs.load('lo')


def test_numbers_found_as_digits_words_and_months():
    src = 'ສະບັບເລກທີ 292/ລບ, ລົງວັນທີ 28/05/2025 ພາຍໃນ 180 ວັນ ແລະ 15 ວັນ'
    en = 'Decree No. 292/GO, dated 28 May 2025, within one hundred and eighty days and fifteen days'
    assert number_problems(src, en, LO) == []               # "one hundred and eighty" is 180
    assert number_problems(src, en.replace('one hundred and eighty', 'one hundred'), LO) == ['180']


def test_lao_digits_and_missing_figure():
    assert number_problems('ມາດຕາ ໒໕ ແລະ 3.000 ໂຕນ', 'Article 25 and 300 tonnes', LO) == ['3.000']


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


def test_ordinals_roman_sections_and_split_figures():
    assert number_problems('ສະບັບທີ 1 ພາກທີ 2', 'the first edition, Part II', LO) == []
    assert number_problems('2.1 ອຸທົກທໍລະນີ', '2.1 Hydrogeology', LO) == []
    assert number_problems('ລະຫວ່າງ 3 0- -45 ແມັດ', 'between 30 and 45 metres', LO) == []
    assert number_problems('1.000 ໂຕນ', '1,000 tonnes', LO) == []


def test_figures_the_pdf_prints_twice():
    assert number_problems('ກວມເອົາ 16 16, 2% 2% ແລະ 20302030', 'accounted for 16.2% and 2030', LO) == []
    assert number_problems('ປີ 2020', 'in 2020', LO) == []


def test_compound_number_words():
    from ai_pdf_translator.check import _word_numbers
    assert _word_numbers('twenty-five days and two thousand five hundred tonnes') == [25, 2500]
    assert _word_numbers('one hundred and eighty') == [180]
