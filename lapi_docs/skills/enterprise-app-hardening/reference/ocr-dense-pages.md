# OCR: dense pages and cut-off answers (Lapi v26.1.16.29)

Symptom: "OCR output was incomplete. Increase LAPI_OCR_MAX_TOKENS and LAPI_OCR_CONTEXT or split the page" on a
dense scanned page (a legal notice). The vision model hit its output budget (`done_reason == 'length'`);
the local 8k context cannot simply take a larger output budget because the image patches use most of it.

Fix that needs no settings: split the page image into a top and a bottom strip at the whitest row near the
middle (PIL: per-row mean brightness via `resize((1, h), BOX)`), transcribe each strip, join with a newline,
recurse at most twice (4 strips), skip blank strips, record `split_parts` in the OCR metadata, and keep the
budget check per strip. Only when the strips are still cut off raise a plain-words error that tells the person
what they can do (lower resolution, searchable PDF) and what an administrator can do (`LAPI_OCR_MAX_TOKENS`).
Partial text is never indexed. Tests fake `ocr.call` and decide by the decoded image height.
