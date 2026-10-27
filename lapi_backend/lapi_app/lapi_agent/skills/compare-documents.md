---
name: compare-documents
description: Side-by-side comparison of two or more documents or saved results, field by field, with differences called out.
allowed_tools: find_extractions, read_extraction_results, compare_records, search_documents, read_document_section, describe_results, update_plan
output_format: A short verdict, then a table with one row per field and one column per item, then a bullet list of notable differences.
---
1. Identify the items to compare from the request (names or IDs). If fewer than two are clear, ask which ones.
2. Prefer saved extraction results: use compare_records with the fields the user cares about; otherwise the common fields.
3. When a field is missing from saved results, search the original documents for it and expand the passage.
4. Mark values that differ. Never fill a missing value; write "not found".
5. Cite every cell value or the row it comes from.
