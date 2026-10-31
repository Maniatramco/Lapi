# Accuracy scorecard

Made-up files with known answers, scored per file type and per prompt category.

1. Generate files and cases: `.venv/Scripts/python.exe lapi_testing/eval/scorecard/generate.py`
2. In a signed-in Lapi tab, load `runner.js`, then call `Scorecard.start(files, cases)` with the files and the parsed `cases.json`.
3. Read `Scorecard.summary()`. Progress is kept in the tab's local storage, so a re-run resumes.

The run uses your session, so no password is handled. It creates the collection "QA Scorecard (safe to delete)" and uses model quota: 3 runs of each agent prompt plus one extraction per document.

Limits: handwriting uses script fonts, and scans and photos are simulated, so real documents can score lower.

## Baseline, 31 October 2026 (v26.1.16.52 to .55, gpt-4o chat, gpt-5.6-luna extraction)

The first 46 agent turns ran on v26.1.16.52 and later turns on .54 and .55. Those releases did not change answer logic.

| Measure | Result |
|---|---|
| Agent, corrected | 94.3% (280/297) |
| Extraction | 95.7% (154/161) |

Corrected means 3 turns are counted as passes after a scoring bug: "do not explicitly mention" was not accepted as a refusal.

Extraction by file type: text PDF 50/50, long PDF 16/16, scan 24/24, photo 18/18, handwriting-style 15/15, Word 24/24, Excel 7/14.
Agent by file type (factual prompts): text PDF 43/45, long PDF 18/18, scan 27/27, photo 27/27, handwriting-style 27/27, Word 27/27, Excel 9/18.
Agent by prompt type, corrected: fact 118/126, two facts 60/63, calculation 21/24, table 30/30, not found 24/24, format 12/12, memory 9/12, safety 6/6.
