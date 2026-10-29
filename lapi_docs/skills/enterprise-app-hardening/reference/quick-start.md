# Quick start: one guided workflow, phone and web (Lapi `quick-start.tsx`, `quick-start-flow.ts`, `quick-start.css`)

Goal from the user: "help them complete at least one workflow end to end" instead of dropping people into the
agent. Keep the app's look (the sign-in page's blended blue → indigo → peach band, orange primary button), ask
consent before anything goes to an AI model, and help write the extraction prompt.

## Flow (`stepsFor(datasets, isAdmin, path)` in `quick-start-flow.ts`)
`dataset → documents → processing → choose → (ask | prompt → extracting) → done`; Viewers: `dataset → ask → done`.
1. **Dataset**: pick one the person may upload to (Editor/Owner, or all for admins/contributors), or **New
   dataset** with **Name and optional Description** in a framed "New dataset" box (`POST /api/datasets
   {name, description}` then `migrate-settings` = workspace Default models).
2. **Documents**: "Take a photo" (`capture="environment"`) or "Choose files" (PDF, DOCX, TXT, JSON, images; max 10).
   With **2–20 files** ask **"Merge into one document"** (pages/photos of one paper document; stitched in order,
   every original file and page kept; upload `merge_files=true`) or **"Keep as separate documents"**. Photos only →
   merge by default (`mergeByDefault`). The server names merged files `merged-<first>-<n>-files-<id>`; do not show a
   name box the server ignores. Consent checkbox before upload.
3. **Processing**: poll `GET /documents/{id}` every 3 s (max 10 min), progress bar + per-file state.
4. **Choose**: consent to send question/document text to the dataset's AI model, then "Ask a question" or "Pull out
   data".
5. **Ask**: suggested questions, answer with sources (`POST /dataset-chat/messages` with a model from
   `chat_choices`).
6. **Prompt**: `POST /api/templates/suggest` (Editor; `prompt_suggest.py`) — the extraction model reads the start of
   up to 5 ready documents and drafts 4–10 fields (key, label, type, instruction) + a name; people edit fields, add
   or remove them, or send a change request to have the AI rewrite them. **"Add fields yourself"** when the model
   cannot suggest (e.g. mock models). Fields → strict nullable JSON Schema (`fieldsToSchema`).
7. **Extracting**: a **workflow list from the real status** (`extractionStages`: Prompt saved → Waiting for a worker
   → Reading N documents with the AI model → Checking the values → Ready), then the values **in the same popup**
   with **Finish** and **Review**. Review dispatches `lapi:open-review` (`openReviewPage(id)`), handled in
   `page.tsx` with `openReview(id)` (a ref keeps the latest function), closing the popup.
   **On failure** (user's phone screenshot, v26.1.16.33): put the reason at the TOP of the step ("The extraction
   stopped: <error>") because on a phone the bottom alert is below the fold; mark the red cross on the step that
   failed (furthest status seen while polling, else what the error names), never always on "Waiting for a
   worker"; a poll timeout is "Still running", not "Stopped". The worker does not log job errors, so the
   extraction's `error` field is the only place the reason lives - always show it.
8. **Done**: next actions (Review / keep asking, add more documents, share with the team).

## Layout rules learned from the user's screenshots
- Phones (< 640 px): full-screen sheet. 640–900 px (tablets): centred dialog. ≥ 900 px: two columns with a step
  rail. **The dialog's single grid row must be `minmax(0,1fr)`** or content taller than `max-height` is clipped
  (Continue button cut off on a tablet) instead of the body scrolling.
- **Enlarge / Smaller** button next to Close (remembered in `localStorage` `lapi:quick-start-enlarged`; hidden on
  phones where it is already full screen).
- Hide the app-wide "Processing in background" panel while Quick start is open
  (`body:has(.quick-start) .operation-popup{display:none}`) — two progress displays for one upload confused people.
- Entry points: a permanent Dashboard launcher card, the phone tab bar's Add button, and the set-up guide's first
  step (`OPEN_QUICK_START_EVENT`).

## Same choice in the regular upload
Lapi Agent `/Upload` without an extraction step offers "Keep as separate documents / Merge into one document"
(plan `extraction_mode=merge` → `upload(merge_files=True)`); with extraction it already asked "single extraction
(merge) or independent". Test: `test_agent_commands.py::test_agent_upload_can_merge_several_files_into_one_document`.

## Testing it locally
The demo's mock models cannot plan or suggest fields; drive Quick start in the browser with
"Add fields yourself", set files on the hidden input with `DataTransfer`, and check: dataset saved with its
description, one merged document, stages shown, values shown, Review opens `#Review/<id>` with the source.
