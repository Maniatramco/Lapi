---
name: invoice-review
description: Check invoices for totals, due dates, duplicates and anomalies across saved results.
allowed_tools: describe_results, aggregate_results, read_extraction_results, find_extractions, compare_records, search_documents, update_plan
output_format: Summary totals first, then a table of invoices that need attention with the reason for each.
document_types: invoice, bill, receipt
domains: finance, accounts payable
keywords: invoices, due date, overdue, duplicate invoice, vat, gst
---
1. Use describe_results to find total, date, vendor and invoice-number fields.
2. Compute totals and counts with aggregate_results (group by vendor or month when useful).
3. Flag invoices that are overdue relative to today, have duplicate numbers, or have totals far from the vendor's usual amount.
4. Cite each flagged invoice. State that saved values are unverified until reviewed.
