# Workbooks: everything read, everything connected

Lapi reads an Excel workbook (`.xlsx`) the way a careful person would: every part of it, each part tied
to the sheet, cell and row it belongs to, and the links between the parts recorded. Chat and extraction
both use that one understanding. CSV and TSV files are plain tables and are read the same way, minus the
parts they cannot contain.

## Rule: nothing is dropped silently

An `.xlsx` file is a zip package of parts. Lapi lists **every** part and gives each one a reader
(`lapi_backend/lapi_app/workbook.py`). A part Lapi cannot read goes on the document's **Not read** list
with the reason; it is never ignored. The list appears in the searchable "What Lapi read in this
workbook" page, in the agent's `workbook_map`, and in the review note of extractions.

## What each part becomes

| In the workbook | What Lapi does | Tied to |
|---|---|---|
| Cell values | Read with their type (number, date, text, yes/no) | Sheet, row, column |
| Formulas | The saved result **and** the formula. If Excel never saved a result (files made by scripts), Lapi calculates it (pycel, plus COUNTA, XLOOKUP, XMATCH, TEXTJOIN, DATEDIF, NETWORKDAYS, WORKDAY, SWITCH, PROPER, MEDIAN, STDEV, RANK, COUNTBLANK that pycel lacks). If it cannot, the cell is listed as not read. | Cell; column formulas are described ("Amount (USD) = ROUND(Amount × FX Rate, 2)") |
| Comments and notes (classic and threaded) | Text and author | Their cell, written into the row's text |
| Hyperlinks | Link target | Their cell |
| Highlight fills and coloured text | "Status highlighted red" | Their cell |
| Hidden rows, columns, sheets | Read and marked hidden | — |
| Dropdown lists, conditional-highlight rules | Recorded in the sheet's meaning profile | Column / range |
| Images (photos, scans, receipts, logos, sheet backgrounds) | Read by the OCR vision model: its text plus a one-line description | The anchor cell and row |
| Charts | Title, type, series and numbers, as a small table (numbers taken from the cells when the file saved none) | Sheet; linked to its source range |
| Text boxes, shapes, SmartArt | Their text | Sheet and anchor cell |
| Embedded files (PDF, Word, Excel, images, text, packaged files) | Unpacked and read like an upload | Anchor cell and row |
| Named ranges, Excel tables | Recorded | — |
| Pivot tables | Their shown values are read as cells, with a note | Sheet |
| Macros (`.xlsm` parts) | Data read; code never run; noted | — |
| Data connections, slicers, timelines, form controls, Power Pivot model, new-style charts | Listed as not read, with why | — |
| Password-protected files | Refused: "remove the password and upload again" | — |

## Relationships

Recorded at upload, each marked **proven** or **likely**:

- **Formula links** (proven): which cells and sheets a formula uses (`Summary!B4 = SUMIFS(Transactions!O:O …)`),
  with the label next to the cell ("Total income") and its value.
- **Keys between sheets**: a column whose values are another sheet's unique key
  (Transactions.Counterparty → Vendors.Name). All values found: proven; most: likely.
- **Chart sources** (proven): the range each series comes from.
- **Items to rows**: an image, text box or embedded file is linked to the row it is placed in (proven), and
  to any row whose identifier it shows, such as an invoice number on a receipt (proven when that value is
  unique; a repeated value such as a vendor name is likely).
- **Agreement**: amounts read from an image are compared with the numbers of the row it belongs to;
  a receipt that says 254.37 for a row of 245.37 is flagged.

## Meaning profiles

Each sheet gets a profile: every column with its type, range or total, the real values of label columns
(Status: Paid, Pending, Overdue…), whether it is an identifier, its formula, its dropdown, and the sheet's
links and attachments. Profiles are searchable and are what the model reads to understand wording that is
not a column name.

## Extraction from spreadsheets

When every document of an extraction is a spreadsheet:

1. The dataset's model matches each field to a column **by meaning** using the profiles
   ("Invoice number" ← Reference No; "Vendor country" ← Vendors.Country through Counterparty).
2. Every proposal is checked: the column must exist, its type must fit the field, and a column on another
   sheet needs a key link. Exact names win without asking.
3. Quick start shows the mapping; the person can change any field (`POST /api/templates/table-plan`, then
   `column_mapping` on the extraction).
4. Values are read exactly from the stored table, one record per row. Fields that are not columns (text on
   a receipt, a comment, a judgement) are read by the model from **each row's own** cells, comments and
   image text, in batches sized to the model; the whole sheet is never sent at once. Fields about the whole
   table (totals) are named and left for chat, which answers them exactly.

## Chat

The agent has two workbook tools besides `query_table`:

- `workbook_map`: profiles, links, calculated cells, items with their rows and any disagreements, coverage.
- `row_context`: one row with its notes, its images/text boxes/files and the matching rows of linked
  sheets, found by row number, item id (`image-1`) or a value (`BILL-2025-0002`).

`query_table` can `join` a linked sheet (or another spreadsheet in the dataset) so a question like
"how much do we still owe vendors in India?" is answered exactly: Transactions joined to Vendors on
Counterparty = Name, Country = India, Status in Pending/Overdue, sum of Amount (USD). The answer states the
mapping and the join it used, and asks one short question when wording is genuinely ambiguous.

## Limits

Up to 20 sheets, 50,000 data rows, 300 images (more are listed as not read), 50 embedded files of up to
40 MB, 2 minutes of formula calculation. Image text is OCR: check names and numbers against the original.
