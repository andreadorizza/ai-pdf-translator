# ai-pdf-translator

A command-line toolbox and an agent skill that translate PDFs (scanned or digital) in Lao and other low-resource languages into English, set in the original layout. Users' agents run it through `skills/ai-pdf-translator/SKILL.md`.

## Before you change anything

- Read `GLOSSARY.md` and use its terms (paragraph, reading, doubt, scan check, batch, term list, review list…) in code, docs and messages.
- Read the decision records in `docs/adr/`. In short: the agent orchestrates and the command is its toolbox (0002); layout and write-back come from PDFMathTranslate, pinned, with runtime patches in `src/ai_pdf_translator/layout.py` (0003); the licence is AGPL-3.0 (0001).
- Judge translation quality only against independent references (the human English in the self-test document, `eval/`), never by asking a model whether a model's output is good.

## Layout

- `src/ai_pdf_translator/`: the package. `cli.py` (commands), `ocr.py` (page kinds, two readings, text layer), `layout.py` (PDFMathTranslate bridge and scan-page writer), `doubts.py`, `plan.py` (paragraph ids, batches, term candidates), `check.py` (scan-check crops, numbers check), `build.py` (merge, PDF, review list), `services.py` (headless mode), `selftest.py`, `langs.py` (language profiles), `prompts/` (instructions the subagents read).
- `skills/ai-pdf-translator/SKILL.md`: the skill for Claude Code, Codex and OpenCode. `agents/`: Claude Code subagents. `.claude-plugin/`: plugin and marketplace files.
- `eval/`: scoring tools and results of past comparisons.

## Commands

- Install for development: `uv sync --python 3.12`
- Tests: `uv run --with pytest pytest -q tests`
- Try it: `uv run ai-pdf-translator prepare <pdf> --pages 5-8 --work /tmp/w`, then the steps in SKILL.md.
