# Evaluation

Scores here come only from independent references: the human English of the Lao carbon-credit decree (2025), automatic metrics (chrF++, BLEU) and a figures check. No model judges another model's output.

- `score_pdf.py`: chrF++ and figures for any tool's translated PDF, article by article. The reference text comes from the decree's English pages (see `ai_pdf_translator.selftest.reference`).
- `pdf2zh/`: PDFMathTranslate on the decree, and the spike that led to ADR 0003 (`RESULTS.md`).
- `score.py`, `facts.py`, `reference.py`, `ocr_compare.py`, `nllb_colab.py`, `common.py`: tools from the pilot (OCR bake-off, model comparison, NLLB baseline); they read the pilot's file formats.
