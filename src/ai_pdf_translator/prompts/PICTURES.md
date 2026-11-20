# Reading the text in pictures

Each contact sheet in the task file shows labels cropped from one picture (a map, a diagram or a chart) of a {language} document. Every row has a red number and a zoomed crop. Open each sheet and give, for every number on it:

- `source`: the text you read (as printed, also when it is not {language})
- `english`: a short English label for it, as a map or chart would show it
- `keep`: true when nothing should change: coordinates, plain numbers, English text, or no text at all
- `erase`: true, with an empty `english`, when the crop is only a fragment (such as an abbreviation alone) whose name is in another row
- `unsure`: true when you are not sure of your reading. Still give your best `english`: a person checks every unsure label.

Keep labels as short as the original. If a crop shows only part of a label, translate the part you can read. {notes}

Write the file named in the task's `output` field, and nothing else, as JSON with one object per picture (the `picture` value of its sheets) and the numbers inside it:

```json
{"p018-49": {"1": {"source": "...", "english": "...", "keep": false}, "2": {"source": "...", "english": "", "keep": true}}}
```
