# Workbooks: everything read and connected (Lapi v26.1.16.35)

User's asks, in order: "if Excel contains images or anything, I should not be missing any info"; questions
and extraction must understand meaning; answers must use the relationships across the workbook; a
question about an image inside the workbook must connect to the rest.

## Design that satisfied it
- Read the PACKAGE, not just cells: list every zip part, map each to a reader, put everything unhandled on a
  "not read" list with a reason (coverage report). Silence is the bug the user cared about.
- Two openpyxl loads (data_only True/False) give values and formulas. Script-made files have no cached
  formula results: calculate with pycel (fast: 4,073 formulas in ~8 s) and add the functions it lacks via
  `ExcelFormula.default_modules += ('lapi_app.excel_functions',)`. pycel pins networkx < 2.7: pin 2.6.3 in
  BOTH requirements files or the local-embeddings build conflicts.
- Drawings XML (xdr) gives anchors for pictures, charts, shapes; chart XML gives title/series/ranges and
  caches (empty for script-made charts: read the referenced cells). Threaded comments live in
  xl/threadedComments with xl/persons. Embedded objects: oleObject in sheet XML + rels; unwrap OLE
  (CONTENTS = PDF, Package = Office, Ole10Native = packager) with olefile.
- Everything attached to a row is written into that row's text (comments, links, highlights, item summary),
  so search/extraction/chat see it with the row. Items, profiles, lineage and coverage are extra pages.
- Relationships with strength: formula refs and anchors are proven; unique key match is proven; value
  overlap / repeated names are likely. Amount agreement between an image and its row is checked.
- Noise to avoid: numbers inside IDs (BILL-2025-0002) are not amounts (money = 2 decimals or thousands
  separators); theme text colour 1 is the default, not a highlight; common words (Paid) are not links
  (only IDs, multi-word names, long words).
- Number items per kind (image-1, chart-1) - ids are what the agent and people refer to.

## Meaning, not names
- Per-sheet meaning profile (types, ranges, real values of label columns, identifiers, formulas, dropdowns,
  links) feeds the model; the model proposes field -> column (or row / whole / none); code checks every
  proposal (exists, type fits, other sheet only via key link) and exact names win. Show the mapping and
  let the person change it (Quick start) before extracting.
- Never send the whole sheet to a model: non-column per-row fields go in batches of row texts sized from
  the model's context and output limits.
- Chat: `workbook_map` first, then `query_table` (with `join`) for numbers, `row_context` for a row, image or
  value; the answer states the mapping and join, and asks one question when wording is a real guess.

## Tests that proved it
A workbook built with openpyxl plus zip injection (text box with explicit xmlns, embedded file via
oleObject + rels, unknown parts) covering formulas without cache, comment, link, fill, hidden row,
dropdown, receipt image (OCR stubbed), chart, two linked sheets; meaning extraction with a stubbed
`providers.plan` that includes a wrong-type and a nonexistent-column proposal; scripted chat calls.
