# Spreadsheets (XLSX, CSV, TSV), exact answers and charts (Lapi v26.1.16.26)

The user's requirement: support Excel and CSV "very carefully" so **column relationships are kept while
embedding**, and let the agent draw charts when asked.

## Reading (`lapi_backend/lapi_app/spreadsheet.py`)
- CSV/TSV: decode UTF-8 (BOM) → cp1252 → latin-1; `csv.Sniffer` over `, ; \t |` (TSV forced to tab).
- XLSX: `openpyxl.load_workbook(data_only=True)` (cached formula values), merged ranges filled from their top-left
  cell (noted), hidden sheets noted; `.xls` (OLE header) refused: "save it as .xlsx or CSV".
- Trim empty trailing rows/columns; detect the header row (mostly text, data below); blank names → "Column C",
  duplicates → "Name (2)"; keep spreadsheet row numbers (header = row 1) so people can find rows in Excel.
- Column types only when every filled cell agrees: number ("1,234.50", "(10)" = -10, currency symbols), ISO date,
  boolean, else text. Limits: 50,000 rows, 200 columns, 20 sheets, 2,000 chars per cell.
- Validate fully **at upload** (main.upload) so errors are immediate; never merge spreadsheets with other files.

## Indexing that keeps relationships
- Per sheet: a **summary chunk** (rows, columns, type, filled count, min/max/total or examples).
- Row chunks: each row is `Row n · Column: value · Column: value` (empty cells skipped); `pack()` fills chunks with
  whole rows only, each chunk starting with `Sheet "X" · columns: A, B, C`; a row too wide is split between
  `Column: value` pairs (`Row n (part k)`). `fits()` uses the embedding model's own limit (MiniLM tokenizer count,
  OpenAI 8,000-byte bound) and table chunks (`table: True`) skip the generic character/token re-splitting.
- Chunk metadata `section` ("Sheet: X · rows a-b"), `sheet`, `row_start`, `row_end`; add them to every place that
  copies chunk fields into citations (knowledge search, legacy providers search, agent `_source_locked`).

## Exact answers
- Store the typed table as Parquet per sheet + `tables.json` manifest (pyarrow).
- `query(store, id, spec)`: validated spec only (no SQL, no code): filters (`= != > >= < <= contains in between
  is empty / is not empty`, case-insensitive text), group by up to 2 columns (dates by day/month/quarter/year),
  metrics count/sum/avg/min/max/count_distinct, or list columns of matching rows (with spreadsheet row numbers),
  sort, limit ≤ 200. Clear errors list the sheets/columns.
- Lapi Agent tool `query_table` (agent_tools_v2 `CONTRACTS`): resolves the document through the access-checked
  scope, cites "Calculated from <file> · sheet <name>", returns the sheet's columns and types so the model can
  correct itself. The Dashboard chat has no tool loop (one retrieval pass) — it benefits from the row chunks and
  summaries; calculations and charts happen in Lapi Agent.

## Charts
- The tool takes an optional `chart` {type bar|line|pie|scatter, title, x, y[]}; columns must exist in the result;
  pies ≤ 8 slices; ≤ 4 charts per answer. Saved on the message as `charts` with the computed rows — **the chart's
  numbers always come from the data, never from the model's text**.
- Frontend `answer-chart.tsx` (SVG, no chart library): round axis ticks, bars/lines/points/slices with titles,
  legend, spoken `aria-label` summary, "Show the numbers" table and "Download data" CSV (numbers kept, text
  starting with = + - @ prefixed with ' so spreadsheets do not run it).

## Tests
`test_spreadsheets.py` (reading, packing, queries, upload + index, refusals, agent tool + chart with a scripted
model), `answer-chart.test.cjs`. In the demo: upload a CSV through the API, inspect chunks in the api container,
feed a scripted chat answer with `charts` to see the rendering.

## Extraction from spreadsheet rows (v26.1.16.34)

Failure seen live: Quick start drafted row fields (Transaction ID, Date, Amount, ...) for a 2,000-row
sheet and sent the whole sheet to a cloud model with a 32K context: "Selected content exceeds this
model's context budget". Raising the limit is not the fix - the output (2,000 records) would not fit
either, and the values are already structured.

- When every document is a spreadsheet and >= half of a flat prompt's fields match columns, read each
  row from the stored Parquet table: one record per row (`{"records": [{source_filename, source_key,
  fields}]}`), values converted to the field type, no model call. Unmatched fields are null and named
  in the evidence notice. Keep the model path for anything else (totals, judgments, nested fields).
- Match by key and by the label before ':' in the field description; exact first, then column words
  inside the field words ("Date" for "Transaction date"), longer column names first, each column once.
- Evidence: one quote per row ("Row N") from the row's search chunk, not one per field (20,000 quotes
  would bloat every poll of the extraction).
- UI: result helpers must unwrap `records[0].fields`; show "record 1 of N"; Review opens on the first
  record instead of rendering every field of every row.
- Diagnose such failures by reading the extraction's `error` (GET /api/extractions/{id} when signed in);
  the worker does not log it.
