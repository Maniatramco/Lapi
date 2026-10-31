# OCR: dense pages read in parts (Lapi v26.1.16.29)

Symptom: "OCR output was incomplete. Increase LAPI_OCR_MAX_TOKENS…" on a dense scanned page (a legal notice).
The vision model hit its output budget (`done_reason == 'length'`); the local 8k context cannot take a much
larger output budget because the image patches use most of it. The user's rules: the person must never see
that error, splitting must not lose relationships (a line, a table header and its rows), and the progress
line must say why it is slow.

Design (`lapi_app/ocr.py`):
- **When**: before asking, `estimate_tokens(row_profile, width)` = ink bands x (width / (0.5 x median band
  height)) / 3.2; split when > 70 % of `LAPI_OCR_MAX_TOKENS`. After asking, still split when the answer
  comes back cut off. Depth 3 (8 strips), min strip height 300 px; only a strip that still overflows raises,
  in plain words.
- **Where**: `choose_cut` takes the white gaps between ink bands in the 25–75 % band, calls a gap a section
  gap when it is >= 2 x the median gap (and >= 6 px), cuts in the middle of the section gap nearest the
  centre; otherwise the widest gap; otherwise the whitest row. A tight table has small gaps, so the cut
  lands above or below it, never between its header and rows, and never through a line.
- **Relationships across the cut**: each lower strip's prompt gets `continuation(prior)` with the last 3
  lines of the text above ("the part above ended with these lines … keep the same columns, order and
  separators; do not repeat them"). Both the Ollama prompt and the cloud instruction get it.
- **Telling the person**: `cfg['_progress']`/`cfg['_page']` are set by `read_page`/`read_image`; `_report`
  calls `progress(page, note)`; the worker's `ocr_progress(page, note=None)` writes the note into the
  extract stage detail ("Page 3 has a lot of text: reading it in parts so nothing is cut off. This takes
  longer." / "Page 3: reading part 2 of 4."). Keep the TypeError fallback for one-argument callbacks.
- Metadata carries `split_parts`; the OCR notice says "read in N parts". Tests fake `ocr.call`, decode the
  image to decide by height, and assert strip heights sum to the page and the cut sits in the gap.
