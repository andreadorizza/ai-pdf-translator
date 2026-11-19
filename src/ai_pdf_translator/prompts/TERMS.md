# Building the term list

`terms/candidates.json` holds {language} phrases that repeat in the document, and the text of its definitions section if it has one. Choose the terms a reader must see translated the same way every time: names of institutions, legal and technical terms, defined terms. Skip ordinary phrases.

Give each chosen term one English rendering. Use the definitions section when it defines the term; otherwise use the usual English name in the field (for a ministry or law, its official English name if you know it).

Write `terms/terms.json`, and nothing else, as JSON: `{"<{language} term>": "<English>", ...}`. Keep it under 150 terms.
