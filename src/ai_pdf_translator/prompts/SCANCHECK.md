# Checking against the scan

Each item in the scan-check file is a paragraph whose source text or translation is in doubt. It gives a crop of the page as printed (a scan, or a digital page whose text layer may lack figures or words the page shows), the extracted text, the current English, and what is in doubt.

For each item, open the crop image, read the {language} in the image carefully (the paragraph is in the middle of the crop; the lines above and below are context), and correct the English so it matches the scan. Change only what the scan shows is wrong. Check every number, date and name in the paragraph against the image.

Write the file named in the check file's `output` field, and nothing else, as JSON:

```json
{"p009_03": {"source_read": "the {language} you read for the doubtful part", "english": "the full corrected English for the paragraph", "changed": true, "unreadable": false}}
```

Set `unreadable` to true when the scan itself is too unclear to decide; a person will check those paragraphs.
