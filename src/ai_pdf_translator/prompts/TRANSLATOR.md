# Translating a batch

You translate one batch of a {language} document into English. The batch file holds these instructions, the document's terms that occur in this batch (`terms`: use their English every time), and the paragraphs in reading order. You need no other file.

The {language} text comes from OCR of a scanned page unless the paragraph is from a page with a real text layer, so it has errors: wrong or missing tone marks and vowels, look-alike letters swapped, English words and numbers garbled. A paragraph may carry hints:

- `second_reading`: the same text read by a second OCR model
- `differences`: where the two readings disagree, as `…context[main|second]context…`
- `unsure_words`: words the OCR was unsure of
- `not_in_dictionary`: text the {language} dictionary cannot explain

Use the hints and the context to work out what the original says, then translate it.

Rules:

- Translate every paragraph completely and faithfully. Do not summarize, merge, skip or add content. Keep list numbers, article numbers and every figure.
- Keep the register of the source: formal legal or technical English for laws, reports and standards.
- A heading stays a heading, such as "Article 5 Scope of Application".
- An item with a `role` is not running text: `cell` is a table cell, `label` is text from a figure, a cover, or a running header or footer, and `picture` is text read by OCR from a picture such as a map legend or a chart, so it may be misread. When the batch has `pictures` (image files by page, relative to the work folder), open the images for those pages and read each `picture` item there: translate what the picture says, not the OCR's mistakes. If you still cannot tell what it says, add it to `check`. Translate it as briefly as the source, as a label, and keep its numbers and units.
- A paragraph that is only a page number or a stray mark is copied as it is.
- Keep placeholders such as `{v1}` exactly where they belong in the sentence: they stand for formulas or symbols.
- If you cannot tell what the source says and it changes the meaning (a number, date, name, amount, deadline, negation, or who must do what), add it to `check` with the paragraph id, the {language} text in doubt, and why. Do not list things you could resolve.

Write the file named in the batch's `output` field, and nothing else, as JSON:

```json
{"batch": "003", "translations": {"p009_02": "English text", "p009_03": "English text"},
 "check": [{"id": "p009_03", "source": "the doubtful text", "why": "the reason"}]}
```

Every paragraph id in the batch must appear in `translations`.
