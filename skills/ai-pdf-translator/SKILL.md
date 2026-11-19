---
name: ai-pdf-translator
description: Translate a PDF into English and keep its page layout, for scanned or digital documents in Lao and other low-resource languages. The OCR is checked, a person gets a review list, and subagents do the translation in small batches so it stays token-efficient. Use when the user wants a PDF, scan or report translated into English, especially from Lao, or wants the translation to look like the original.
---

# Translating a PDF with ai-pdf-translator

The `ai-pdf-translator` command does all the work that needs no model: sorting pages, OCR, finding paragraphs and doubts, cropping the scan, writing the PDF. You orchestrate the model work with subagents. Never read batch, translation, paragraph or crop files into your own context: give their paths to subagents and read only the command's short summaries. That keeps a 100-page document cheap.

## 1. Setup (once per machine)

1. If `ai-pdf-translator --help` fails, install it: `uv tool install git+https://github.com/andreadorizza/ai-pdf-translator` (install `uv` first if it is missing: https://docs.astral.sh/uv/).
2. Run `ai-pdf-translator setup`. If it reports something missing, run the install command it prints (Tesseract and its Lao models; on macOS `brew`, on Debian or Ubuntu `apt-get`), then run `setup` again. The first run also downloads a layout model.

## 2. Prepare

Run `ai-pdf-translator prepare <file.pdf>`; add `--pages 1-20` for part of a document and `--lang` for a language other than Lao (built in: `lo`, or a profile file). It prints the work folder (call it W), the page kinds, the number of paragraphs and batches. Tell the user these numbers. Only Lao is tested: for another language, say the result is experimental.

## 3. Term list

Start one subagent with a small, cheap model (in Claude Code: the `pdf-translator` agent, or `model: haiku`):

> Work folder: W. Follow W/TERMS.md: read W/terms/candidates.json and write W/terms/terms.json. Reply with one line: the number of terms.

When it is done, run `ai-pdf-translator batches W`: it puts into each batch the terms that batch uses, so every translator uses the same English.

## 4. Translate the batches

Start one subagent per file in W/batches/ (names `001.json`, `002.json`, …), several at a time, each with a small, cheap model (in Claude Code: the `pdf-translator` agent, or `model: haiku`):

> Translate W/batches/NNN.json: follow the instructions inside it. Write only the file named in its "output" field (relative to W). Reply with one line: paragraphs translated and items in "check".

Each batch file holds everything the subagent needs, so it reads one file and writes one. Do not split batches smaller: every subagent has a fixed cost. A batch file with a `pictures` field holds text read from pictures (map legends, charts): give it a subagent whose model reads images (in Claude Code: `model: sonnet`), so it can read the pictures and fix the OCR.

Then run `ai-pdf-translator status W`. Start a subagent again for any batch it lists as left.

## 5. Scan check

Run `ai-pdf-translator crops W`: it crops the page as printed for every paragraph in doubt, on scans and on digital pages (a text layer can lack figures the page shows). For each scan-check file it prints, start a subagent with a model that reads images (in Claude Code: the `pdf-scan-checker` agent, or `model: sonnet`):

> Work folder: W. Follow W/SCANCHECK.md for W/scancheck/NNN.json; open each image with your file-reading tool. Write only the file named in its "output" field. Reply with one line: items changed and items unreadable.

## 6. Build

Run `ai-pdf-translator build W`. It prints the translated PDF, a bilingual PDF, three Markdown files (the English, the source text, and both together paragraph by paragraph, with tables as Markdown tables) and the review list with its number of items. Give the user the paths.

## 7. Review with the user

The review list (W/review.md) holds what a person must verify: paragraphs the scan check could not read, figures in the source that the English lacks, translator doubts that were not checked, and anything not translated. Go through it with the user a few items at a time. For a correction:

- corrected English: add `"<id>": "<English>"` to W/fixes.json
- corrected source text: add `"<id>": {"source": "<text>"}` to W/fixes.json

Then run `ai-pdf-translator apply W`. English fixes rebuild the PDF with no model call. Source fixes create a batch in W/batches/fix-NNN.json: translate it as in step 4, then run `build` again.

## Running again after an update

If the user runs `prepare` again on the same PDF (for example after updating ai-pdf-translator), move the old work folder aside first, then run `ai-pdf-translator reuse W <old work folder>`: unchanged paragraphs keep their English, doubts and scan checks, and `batches` plans only the new text.

## Without subagents

If subagents are not available, or the user prefers an API key, run the whole translation in one command:
`ai-pdf-translator translate W --service anthropic --model <translator> --check-model <image-reading model>` (or `--service openai --base-url <url>` for an OpenAI-compatible API). It needs ANTHROPIC_API_KEY or OPENAI_API_KEY.

## Self-test

To check a model or service on Lao before a real job, run `ai-pdf-translator self-test`: it downloads the Lao carbon-credit decree (2025), published by GGGI with an English version on pages 29–56, and prepares pages 5–8. Do steps 3 to 6 on the work folder it prints, then `ai-pdf-translator self-test --score W`. It prints four lines: pass or fail, the score against the human English, figures matched, and time.
