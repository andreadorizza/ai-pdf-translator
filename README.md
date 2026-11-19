# ai-pdf-translator

AI PDF translator for scanned and digital documents in Lao and other low-resource languages. It gives your coding agent (Claude Code, Codex or OpenCode) the tools to translate a long PDF into English cheaply, keeps the page layout, and tells a person exactly what to check.

- **Checked OCR.** Scanned pages are read twice by two Tesseract models. Where they disagree, or a figure or an unknown word appears, the paragraph is marked as a doubt. A model then compares only those paragraphs with a crop of the scan.
- **Token-efficient translation.** The command does everything that needs no model. Your agent's subagents translate the document in batches of whole sections, on a small model, with one shared term list. A 100-page document never passes through the main agent's context.
- **The original layout.** The English is set into each paragraph's place on the page, and into table cells, figure labels, covers and running headers on digital pages. Layout detection comes from [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate). Images, stamps and signatures stay. You also get a bilingual PDF, and the text as Markdown: the source, the English, and both together.
- **A review list.** It lists paragraphs the scan check could not read, figures in the source that the English lacks, and translator doubts nobody checked. You correct them with `apply`, with no further model runs.

## Results

All scores are chrF++ against a human English translation; no model judges another model.

On a scanned Lao decree with an English version (the 60 articles all outputs share):

| Pipeline | chrF++ | Figures right |
|---|---|---|
| This tool (pilot, Claude Haiku + Sonnet scan check) | 66.3 | 218/218 |
| PDFMathTranslate + Google Translate, our OCR models | 55.0 | 217/218 |
| PDFMathTranslate + Google Translate, its own Lao OCR | 52.0 | 207/218 |
| NLLB-200 3.3B on our OCR (scored in the pilot, all 66 articles) | 52 | — |

Details are in [eval/](eval/). Only Lao is tested. Other languages work through a language profile and are experimental until they pass a self-test.

## Install

In Claude Code:

```
/plugin marketplace add andreadorizza/ai-pdf-translator
/plugin install ai-pdf-translator@ai-pdf-translator
```

In Codex or OpenCode, or for Claude Code without the plugin, install the command, then copy the skill into your project:

```bash
uv tool install git+https://github.com/andreadorizza/ai-pdf-translator
ai-pdf-translator install-skill
ai-pdf-translator setup
```

`setup` checks Tesseract and its Lao models, prints the install command if they are missing (`brew` on macOS, `apt-get` on Debian or Ubuntu), and downloads the layout model. It needs Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/).

## Use

Ask your agent to translate a PDF: the skill tells it what to run. The steps are:

```
ai-pdf-translator prepare report.pdf      # pages, OCR, paragraphs, doubts, term candidates, batches
  (a subagent writes the term list)
ai-pdf-translator batches report.translation
  (one subagent per batch translates)
ai-pdf-translator crops report.translation   # crops of the scan for paragraphs in doubt
  (subagents compare them with the scan)
ai-pdf-translator build report.translation   # translated PDF, bilingual PDF, Markdown, review list
ai-pdf-translator apply report.translation   # after a person's fixes in fixes.json
```

Without an agent, with an API key: `ai-pdf-translator translate report.translation --service anthropic --model <model> --check-model <model>` (or `--service openai --base-url <url>` for any OpenAI-compatible API).

## Self-test

`ai-pdf-translator self-test` downloads the Lao carbon-credit decree (2025) from [GGGI](https://gggi.org/wp-content/uploads/2026/01/Decree-on-Carbon-Credits_PM-Signed_Lao-and-Eng-1.pdf), which has a human English version, and translates pages 5–8. It prints whether your agent or service passes on Lao: chrF++, figures matched, and time.

## Status

Version 0.1. Tested: scanned and digital Lao PDFs, agent mode in Claude Code. Not yet translated: text inside raster images (maps, chart pictures) and tables on scanned pages beyond their text. Not yet tested: headless mode, Codex, OpenCode, rotated pages, languages other than Lao. See the issues.

## Licence and credits

AGPL-3.0, because PyMuPDF and PDFMathTranslate are AGPL (see [docs/adr](docs/adr/)). Built on [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate), [Tesseract](https://github.com/tesseract-ocr/tesseract), [PyMuPDF](https://github.com/pymupdf/PyMuPDF) and [LaoNLP](https://github.com/wannaphong/LaoNLP).
