# Scanned Document Translation

Turns PDFs in low-resource languages, often scanned, into English set in the original page layout, with a list of what a person must still verify.

## Documents and pages

**Source document**:
The PDF a user wants translated.
_Avoid_: input file, original

**Page kind**:
How a page's text can be obtained: a *text page* has a usable text layer, a *scan page* has only an image or a broken font, a *target page* is already in the target language and is skipped, and a *blank page* has nothing to translate.
_Avoid_: page type, digital page

**Paragraph**:
One paragraph of a page, with its box on the page; the unit that is read, translated and written back. Its id gives the page and position, such as `p009_03`.
_Avoid_: block, segment, chunk, region

## Reading the text

**Reading**:
One OCR result for a paragraph; the *main reading* is the one translated, the *second reading* comes from another OCR model and is used to spot errors.
_Avoid_: OCR output, alt text

**Doubt**:
A reason to distrust a reading: the readings differ, the OCR was unsure, the text is not a word, the text is junk, or it holds a number.
_Avoid_: flag, hint, warning

**Batch**:
A group of consecutive whole sections of the source document that one subagent or one call translates together.
_Avoid_: chunk, part

**Text layer**:
The invisible source-language text that the tool puts on a scan page from the main reading, so the layout step can find paragraphs and their boxes. Corrections from the scan check go into the translation, not into the text layer.
_Avoid_: checked text layer, OCR layer

**Scan check**:
A model reading the crop of the scan for a doubtful paragraph, to correct its translation.
_Avoid_: escalation, check, verification

**Term list**:
The document's recurring source-language terms with one agreed English rendering each, built before translation and given to every translator.
_Avoid_: glossary (that word is taken by this file), dictionary, term base

## Results

**Review list**:
What a person must still verify after a run: paragraphs the scan check could not read, figures missing from the English, translator doubts no scan check covered, and paragraphs that failed to translate.
_Avoid_: report, warnings

**Translated PDF**:
The source document's pages with the English set in place of each paragraph.
_Avoid_: output PDF, overlay

## Configuration

**Language profile**:
Everything the tool needs for one source language: OCR models, script range, dictionary and heading patterns, plus whether it is tested.
_Avoid_: language config, lang settings

**Self-test**:
A short run on a public document that has a human translation, which tells a user whether their translation service is good enough for a language.
_Avoid_: benchmark, eval, test set

**Translation service**:
What produces the English: a coding agent's command-line tool or a provider API.
_Avoid_: backend, provider, engine
