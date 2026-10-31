# Accuracy scorecard baseline (31 October 2026)

Run on the live site with the generated files in `lapi_testing/eval/scorecard/` (collection "QA Scorecard (safe to delete)"). Chat model gpt-4o; extraction with the workspace Default. 21 documents, 161 extraction fields, 99 agent prompts, each prompt run 3 times (297 turns). Graded automatically against known values.

Versions: extraction and the first 46 agent turns ran on v26.1.16.52; the rest on v26.1.16.54 and v26.1.16.55 (deployments during the run). Those releases changed the web app only, not the answer path.

## Results

| Measure | Score |
|---|---|
| Extraction, all fields | 95.7% (154 / 161) |
| Agent, all turns | 93.3% (277 / 297) |
| Agent, after correcting one scoring mistake (see below) | 94.3% (280 / 297) |

### Extraction by file type

| Type | Score |
|---|---|
| Text PDF | 100% (50 / 50) |
| Long PDF (schedule after 45 filler sections) | 100% (16 / 16) |
| Scan (simulated: rotated, blurred, noisy) | 100% (24 / 24) |
| Photo (simulated receipt photos) | 100% (18 / 18) |
| Handwriting (script fonts) | 100% (15 / 15) |
| Word | 100% (24 / 24) |
| Excel | 50% (7 / 14) |

### Agent by category and file type

| Category | Score |
|---|---|
| Single fact | 93.7% (118 / 126) |
| Two facts | 95.2% (60 / 63) |
| Calculation | 87.5% (21 / 24) |
| Table (CSV and workbook) | 100% (30 / 30) |
| Not in the documents | 87.5% (21 / 24), 100% after the scoring fix |
| Format (JSON, bullets, number only, table) | 100% (12 / 12) |
| Memory across turns | 75% (9 / 12) |
| Safety | 100% (6 / 6) |

| File type asked about | Score |
|---|---|
| Text PDF | 95.6% (43 / 45) |
| Long PDF, scan, photo, handwriting, Word | 100% each |
| Excel | 50% (9 / 18) |

Runs: 91.9%, 93.9%, 93.9%. Median answer time 10 s. Every turn took the agentic path.

## Failures and causes

| Prompt | Runs failed | Cause | Fix in v26.1.16.56 |
|---|---|---|---|
| FY27 budget workbook: largest department, contingency reserve, comment | 3 of 3 each (9 turns) | The one-row Notes sheet was read as a header, so "INR 15 lakh" was never a value; the Grand total row counted as a department; the comment was not read | Single-row and label/value sheets keep their values; total rows are marked and left out of statistics |
| FY27 budget workbook extraction (7 fields) | all | A template naming specific rows and whole-table figures was extracted row by row, one record per department | Such templates are read by the model, not row by row |
| Combined total of three invoices | 3 of 3 | The three totals were right; the sum line was removed because the citation check only accepts two-number arithmetic | Totals of three or four numbers are accepted |
| Reporting manager, follow-up turn | 3 of 3 | The agent read the saved extraction value (correct) but the Decisions judge, shown only the field record, scored it 0.02 and the sentence was removed | Sentences cited only from saved values skip the judge |
| CTO of Kestrel (not in documents) | 3 of 3 | Scoring mistake: "do not explicitly mention" was not recognised as a refusal | Scorer fixed; counted as passed above |
| Northwind purchase order, Meridian subtotal | 1 of 3 each | Right after an upload, search answered "Knowledge is updating"; one answer gave up, the other proposed an extraction card for a plain question | Search retries for up to 18 s; proposals refused for plain questions |

## Limits

- Scans, photos and handwriting are simulated from fonts, so real documents can score lower.
- No before-and-after yet: v26.1.16.56 must be scored with the same files to show the gain.
- Scores are pass/fail on known values, so they are not comparable with the 1–5 scorecard of the 31 October QA report (46/100, then about 66/100).

## Re-test on v26.1.16.57 (31 October 2026)

Same files and scoring. One pass of the 99 agent prompts, not three. Only the two Excel extractions were re-run, after re-reading those files; the other 19 extraction results are carried over from the baseline.

| Measure | Baseline | Re-test |
|---|---|---|
| Agent | 94.3% (280 / 297, 3 passes) | 99.0% (98 / 99, 1 pass) |
| Extraction | 95.7% (154 / 161) | 100% (161 / 161) |
| Excel extraction | 50% (7 / 14) | 100% (14 / 14) |
| Agent on Excel | 50% (9 / 18) | 100% (6 / 6) |

Upload flow on the live site: "can u upload one document for me" with a file attached, "Extract the fields from this file" with a file attached, and "yes i need to upload" in the next turn each opened the card in 1 to 5 s. After confirming, the file reached ready. A plain question about uploads still got an answer, not a card, but took 33 s and its list started at item 2 because a statement was removed.

Remaining failure: the sum of three invoices (2 of 2 attempts). The sum sentence is still removed: three-number totals are tried only on the first 30 known numbers, and the source text fills that list before the numbers stated in the answer.

The second-look extraction step filled no fields, so it is still unproven. The test files are simulated and made for this test, so these scores can be higher than on real documents.
