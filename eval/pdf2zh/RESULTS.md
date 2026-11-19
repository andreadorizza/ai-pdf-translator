# PDFMathTranslate on the Lao decree (2026-11-19)

PDFMathTranslate at commit 86912e2 (GitHub main, 1.9.12; its OCR is not on PyPI yet), Google Translate (its free default), Lao → English. Input: decree page 2 (broken text layer) and pages 5–24 (image-only scans). Scored with `pilot/score_pdf.py` against the decree's human English, on the 60 articles every output has.

| Run | OCR | Translator | chrF++ | Numbers | Time, 20–21 pages |
|---|---|---|---|---|---|
| Our pilot (`pilot/run2`) | Tesseract `script/Lao+eng`, two readings, scan check | Claude Haiku 5.5, whole articles | **66.3** | **218/218** | 4.5 min |
| PDFMathTranslate A | Tesseract `lao`, tessdata_fast 4.1.0 | Google, per paragraph | 52.0 | 207/218 | 15 min (2 threads) |
| PDFMathTranslate B | our `Lao+eng` models | Google, per paragraph | 55.0 | 217/218 | 24 min (2 threads) |

Findings:

- `-li lo` fails: the code maps `lo` to a Tesseract model named `lo`, which does not exist (it is `lao`). Runs A and B set `PDF2ZH_OCR_LANGUAGE`.
- Page 2 has a text layer with no Lao letters, so it skips OCR: the Lao stays untranslated and stray page numbers are printed over it (`compare_p2_scan_pdf2zh.png`).
- The final font subsetting crashed (PyMuPDF `ValueError: bad 'value'`). With `--skip-subset-fonts` each output PDF was 3.2 GB.
- In the output's text layer, punctuation maps to U+1C7E–U+1C9F, so copied text is garbled; the page itself looks right. `score_pdf.py` maps it back before scoring.
- Layout is about as clean as ours, but article headings shrink to very small type (`compare_p9_scan_ours_pdf2zh.png`).
- Our OCR models gave +3 chrF++ and fixed 10 of 11 missed numbers; the rest of the gap is the translator and per-paragraph translation. Google turned "carbon credit" into "coal industry" and "carbon fiber" on page 9.
- Translators are a fixed list in `converter.py` and each paragraph is a separate call, so an agent cannot supply translations without a code change or a runtime patch (see the spike below).

`outA/text.json` and `outB/text.json` keep the text of each output page; the 3.2 GB PDFs were deleted.

## Spike: our text layer and our translations through PDFMathTranslate (pages 9–10)

`spike_textlayer.py` puts Tesseract's invisible Lao text (standing in for our checked text) on the scan, then runs PDFMathTranslate's OCR-page path with two runtime patches and no fork: pages with an image and a text layer count as OCR pages, and a translator class of ours records each paragraph (pass 1) or returns our pilot's English (pass 2).

- It works: 29 paragraphs against our 26 blocks, and the English lands in the layout (`spike2_page9.png`, `spike2_page10.png`).
- Lao tone and vowel marks above and below the line show around the white boxes: the boxes follow Tesseract's word boxes, which leave out stacked marks.
- Font subsetting crashed again, so each 2-page output was 235 MB; the PDFs were deleted.
