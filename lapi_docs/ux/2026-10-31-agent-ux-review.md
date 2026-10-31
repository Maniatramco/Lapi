# Lapi agent UX review · 31 October 2026

Scope: the Lapi Agent, Quick start and set-up chat, Review, Files & processing, Jobs, Access and the sign-in flow, reviewed against the eleven agentic-UX rules at phone (375 px), tablet (768 px) and desktop (1,280 px) widths. Code as of `phase2-hardening` at v26.1.16.51. Nothing was changed.

Paths: `FE/` = `lapi_frontend/app/`, `BE/` = `lapi_backend/lapi_app/`, `AG/` = `lapi_backend/lapi_app/lapi_agent/`.

How this was checked: every finding below was read in the source and carries a file and line. The live width check could not be run: the local Next.js install only has Linux build binaries, so the dev web server does not start on this machine, and there is no npm here to fetch the Windows one. The existing Playwright suite covers 390, 768 and 1,440 px for ten screens with a no-horizontal-scroll assertion, but runs on a desktop profile only, so the touch-tablet path is never exercised.

## 1. What the agent really does

**Two chat engines.** With `LAPI_CHAT_MODE=auto` (the OCI setting) a cloud model with function calling takes the plain tool-calling loop in `AG/agentic_chat.py`; Ollama models, explicit operations and running goals take the LangGraph router in `AG/agent_graph.py`. Both end in the same answer checks (`answer_check.py`, `answer_support.py`).

**Tools.** 29 tools in `AG/agent_tools_v2.py:254-314`. 25 read: catalogs, documents, saved results, hybrid search, spreadsheet calculations, workbook maps, row context, comparisons, skills, history. 4 only propose: `prepare_workflow`, `prepare_recovery`, `prepare_dataset_onboarding`, `propose_instruction_update`. The model cannot run a mutation; every proposal becomes a card the person confirms (`AG/agent_workspace.py:771,783`). The router path has 16 tools (`AG/agent_tools.py:82-99`).

**Where the person is asked.**
- Workflow card "A few details to continue": collection, documents, template, merge mode, extraction mode and name are editable before "Confirm upload / extraction / re-extraction" (`FE/agent-v2.tsx:519-529`).
- External processing consent dialog before a workflow, onboarding or re-extraction (`FE/agent-consent.tsx`). Chat turns never ask; the server forces `allow_external` (`AG/agent_workspace.py:517,621`).
- Instruction proposal: before/after with Save only (`FE/agent-v2-chat.tsx:59-67`).
- Clarification: plain text from the model, no choices (`AG/agent_graph.py:137-141`); missing inputs become a guided step with chips (`FE/agent-v2.tsx:302-305`).
- Set-up chat: scripted stages, answers read by the Default chat model; team workspace and collection are created the moment the person answers, with no confirmation step (`FE/setup-chat.tsx:133,145`).

**Stop.** One AbortController per answer (`FE/agent-v2.tsx:351,587`). The server sets a stop flag on disconnect; `delta()` raises on the next piece (`AG/agent_workspace.py:639-641,689`). On the plain loop, pieces are only emitted after the whole answer is finished (`AG/agentic_chat.py:405-410`), so a stop takes effect only once all model and tool calls have completed, and the finished answer is then discarded with empty text. Partial text is kept on the plan record as `chat.status='aborted'`, never in the conversation.

**Progress.** Steps are appended as they start (`AG/agent_progress.py:14-37`), so upcoming steps are never known. The browser gets SSE `progress` and `delta` events with a 1 s heartbeat and no client timeout; workflows use an EventSource that the server closes after about 3 minutes; jobs are polled every 4 s.

**Long work.** Confirmed workflows and goal answers continue on the worker without a browser (`BE/worker.py:393-397`, `AG/agent_goals.py:42-126`). Plans are restored from sessionStorage on reload. Past results: Review directory, Jobs & activity, the Recent chats rail.

**Failure.** Chat errors arrive as an SSE `error` with `message.error.detail`; workflow calls carry `status='failed'` and advice chips (`FE/agent-v2.tsx:509-516`). Job retry re-queues the failed stage and reuses parsed text for indexing (`BE/main.py:950-991`, `BE/worker.py:275-279`).

## 2. Problems

Severity: **high** blocks or misleads a core task, **medium** hurts trust or efficiency, **low** is polish.

### High

| # | Screen | Where | Rule | Problem | Fix |
|---|---|---|---|---|---|
| H1 | Lapi Agent | `AG/agentic_chat.py:405-410`; `AG/agent_workspace.py:639-641,689` | 2, 3, 6 | On the production chat path, Stop, a reload or a lost connection lets every model and tool call run to completion (and bill), then throws the finished answer away as "Stopped before an answer was generated". The person pays for an answer they never see. | Check the stop flag between loop steps; on a disconnect finish the turn and save the answer to the conversation instead of discarding it. |
| H2 | Lapi Agent | `FE/agent-v2.tsx:43,202-208,491`; `FE/agent-answer-workflow.tsx:60` | 6, 1 | Reloading during an answer never re-attaches or polls: `active()` only looks at workflow calls and goals. If the page loads before the server saves the aborted state, the chip shows "Response ready" with a check mark and no answer and no Retry. | Treat `phase==='answering'` as active and re-subscribe or poll; never default the chip status to `completed`. |
| H3 | Lapi Agent | `FE/agent-v2.tsx:339,351,587`; `FE/page.tsx:409` | 2, 10 | Stop appears only after the plan POST returns, and that POST may wait up to 630 s. Running uploads, extractions and goal answers ("even if you close this page") have no Stop or Cancel in the thread; "End this request" appears only after a failure. | Create the controller before the POST; show Stop or Cancel whenever the thread is busy; cancel running jobs with the Jobs-board wording. |
| H4 | Review | `FE/extraction-review.tsx:52,90,125`; `BE/main.py:828,839` | 3, 4, 9 | The only save button is "Reviewed"; its tooltip reads "Save and permanently lock this result". One click saves edits and locks for ever, with no confirmation and no way to save a draft. Viewers can edit and only get a 403 on save. | Separate "Save changes" from "Mark reviewed", confirm the lock with a summary of changed fields, and make the screen read-only below Editor. |
| H5 | Template helper | `FE/template-helper.tsx:20` | 3 | "From the document" posts document text to the external model with `allow_external:true` hard-coded and no consent dialog, unlike re-extract and onboarding. Same pattern in the knowledge-index Retry (`FE/knowledge-index-banner.tsx:31,41`, tooltip only). | Route both through `useAgentConsent().request(...)`. |
| H6 | Lapi Agent | `FE/agent-v2-chat.tsx:101`; `AG/agentic_chat.py:315,351,418`; `AG/agent_progress.py:28-33` | 4 | The answer check result (`validation.answer_support` = passed / skipped / unavailable / not configured, `result` = passed / repaired / removed) is never shown. When the Decisions check is unavailable the step still ends `completed`, so "Check & save" shows a tick and the chip says "Response ready". | Show a source-check line under the answer and mark the phase as a warning unless it passed. |
| H7 | Lapi Agent | `AG/agentic_chat.py:209,211-218,267,301` | 4 | Failed lookups are hidden: a failed pre-search is dropped silently, tool exceptions become `{'error':…}` for the model while the progress step completes, and the evidence budget and step limit are told only to the model. `tool_trace` is never read by the UI. | Mark a step failed or partial when a tool in it errored; show "Some lookups failed: …" next to the answer. |
| H8 | Lapi Agent upload | `AG/agent_workspace.py:816`; `BE/main.py:330,366`; `FE/agent-v2-output.tsx:27` | 8, 5 | The API's per-file `rejected:[{name,reason}]` list is dropped when the call result is built. A non-UTF-8 TXT, a damaged file or a broken spreadsheet vanishes while the request bubble still lists it and the result says "N uploaded document references". | Save `rejected` on the call and show "Not added: name — reason" with an attach-again action. |
| H9 | Files & processing, chat, Review | `BE/worker.py:77,114`; `FE/admin-documents.tsx:94` | 8, 4 | With OCR off, image and scanned pages get `ocr_pending` but the document still becomes `ready` and shows "Native text". Nothing says pages were skipped; `ocr_pending` is not read anywhere in the frontend. | Return an unread-page count and show "3 pages not read (OCR off)" in Files, Needs attention and citations. |
| H10 | Lapi Agent, Collection chat | `FE/agent-v2-chat.tsx:47-57`; `AG/prompts/agent_system.md:23,34` | 8 | The prompt tells the model to answer comparisons with tables and `compare_records` returns one, but the renderer handles only headings, bullets, numbers and code. Pipe tables print as raw `\| a \| b \|` lines with no header or scroll box. | Parse pipe tables into `<table>` with a sticky header inside an `overflow-x:auto` wrapper, as the chart table already does. |
| H11 | Everywhere | `FE/session-request.ts:19`; `FE/chat-login-session.ts:6-16`; `FE/page.tsx:438-443,726` | 9 | On a 401 the client only throws "Your session expired…"; the person stays in the shell with no sign-in action while polling fails quietly. Signing in again drops the `#View` hash and clears the open conversation; the composer draft and unsaved Review edits are lost. | Show a sign-in dialog over the current screen, keep the draft and edits in sessionStorage, restore the hash and conversation after sign-in. |
| H12 | Whole app on touch tablets | `FE/screens-client.ts:6-9,13,22-28`; `FE/page.tsx:248,256,289`; `FE/agent-v2.tsx:106` | 10 | Layout follows pointer type, not width: any touch screen up to 1,100 px (iPad landscape at 1,024) is a "phone". Dashboard is removed for everyone including administrators, non-admins get only the phone screens, and the model list is cut to phone-enabled models. This was a deliberate choice in v26.1.16.40, so it needs your decision. | Decide layout by width alone (phone < 600, tablet 600–1023, desktop ≥ 1024); use `pointer: coarse` only to enlarge targets. |
| H13 | Lapi Agent at exactly 640 px | `FE/screens-client.ts:8` vs `FE/phone-design.css:3,165`; `FE/agent-v2.tsx:470,544,583` | 10 | CSS `(max-width: 640px)` includes 640 but JS uses `width<640`. At 640 the toolbar and model picker are hidden while the phone scope chip and options sheet are not rendered, and the rail is hidden too: no way to change collection, model or history. The unit test locks this in (`deviceFor(640)==='computer'`). | Derive the device from `matchMedia(PHONE_LAYOUT)` or use `639.98px` in CSS; update the test. |

### Medium

**Rule 1 · visible work**
- M1 Raw tool names and statuses in the thread: `<code>{tool.tool}</code>` ("upload", "reextract") and raw "completed / failed / cancelled" (`FE/agent-v2.tsx:500,502,608-609`); raw `job.status` in Jobs (`FE/jobs-board.tsx:84`) and Files (`FE/admin-documents.tsx:16`).
- M2 Two label maps disagree and one is incomplete: `AG/agent_progress.py:5` labels 16 of 29 tools, so on the router path spreadsheet calculations show as "Checking application state"; `AG/agentic_chat.py:26-37` covers all 29 but falls back to the raw name for new tools (`:232`).
- M3 Jargon step labels shown as-is: "Chat Agent · Querying vector knowledge", "Hybrid search", "Reranking evidence", "Routing to Extract Agent", "Resolving authorized chat model"; labels say "dataset" while the UI says "collection" (`AG/chat_agent.py:107`, `AG/chat_knowledge.py:105,122`, `AG/agent_graph.py:188`, `AG/dataset_chat.py:193`).
- M4 The inline status always says "Thinking…": the streaming message never receives `answer_workflow`, so `answerPhase` never sees the running step (`FE/agent-v2.tsx:350,358`; `FE/chat-phase.ts:5`).
- M5 "Response ready" with a tick next to workflows that are still running or awaiting confirmation (`FE/agent-answer-workflow.tsx:60`; `FE/agent-v2.tsx:491`).

**Rule 2 · control**
- M6 No guidance mid-run: Enter shows "Wait for it to finish, or press Stop" while Send is disabled, and during workflows there is no Stop to press (`FE/agent-v2.tsx:578,587`).
- M7 Clarifying questions are joined with " · " in small muted text (`FE/agent-v2.tsx:498`).
- M8 Declining the consent dialog pauses the workflow silently (`FE/agent-v2.tsx:256`).

**Rule 3 · approval**
- M9 The consent dialog lists destinations only: not which files or collection, how many, that sending cannot be recalled, or a cost range beyond "Provider charges may apply" (`FE/agent-consent.tsx:16-19`).
- M10 Chat turns always send retrieved text to the model with no per-request approval; disclosed only in a collapsed footer (`FE/agent-v2.tsx:317,593`).
- M11 Database activation ("Activate OCI database / Local database") switches the API and worker database in one click (`FE/storage-configuration.tsx:37`).
- M12 Permission changes save without a summary of what changes, and nothing warns an owner removing their own access (`FE/dataset-members.tsx:25,40`; server guard not verified).
- M13 The role form preselects Administrator for any non-admin, and the success text says "a User" for an Auditor (`FE/user-management.tsx:44,74`).
- M14 Retries that re-run paid model calls have no warning: Jobs Retry, Needs-attention Retry, "Resume with latest saved prompt", "Restart workflow" (`FE/jobs-board.tsx:91`; `FE/needs-attention.tsx:78`; `FE/extraction-review.tsx:102`; `FE/agent-v2.tsx:501`).

**Rule 4 · trust**
- M15 The collection chat's "partial index" notice (`index_notice`) is returned but never rendered (`AG/dataset_chat.py:146-147,176`; `FE/dataset-knowledge-chat.tsx`).
- M16 Citations of saved extractions hide whether the value was reviewed, although `review_status` is sent (`FE/agent-v2-chat.tsx:109`; `FE/citation-panel.tsx:70`; `AG/agent_tools_v2.py:808`).
- M17 Review edits show no before/after: only a highlight and a count; the old value is never shown (`FE/extraction-review.tsx:107,111,125`).
- M18 A failed partial answer is not labelled where the text is; the error says the partial response is "kept below" but it renders above (`FE/chat-stream.ts:28`; `FE/agent-v2-chat.tsx:98,108`).
- M19 "Note: N statements were removed…" is plain text at the end of the answer, easy to miss, and the same wording is used when the Decisions judge rejected a cited sentence (`AG/answer_check.py:257`).

**Rule 5 · failure**
- M20 Validation errors shown as raw JSON when `detail` is not a string; "Request failed (502). Check the API service." (`FE/page.tsx:435-442`).
- M21 The chat stream has no timeout: a stuck model keeps the spinner for ever behind the 1 s heartbeat (`FE/chat-stream.ts:19`; `FE/page.tsx:455-457`).
- M22 Onboarding polls for ever and its Close is disabled while busy (`FE/agent-onboarding.tsx:65-71,86`). Quick start likewise cannot be closed while it polls for up to 10 minutes (`FE/quick-start.tsx:64,180,195`).
- M23 The workflow EventSource has no `onerror`: a broken events endpoint reconnects silently while the plan looks live (`FE/agent-v2.tsx:290-291`).
- M24 A failed extraction says "Results appear here automatically when processing completes." (`FE/extraction-review.tsx:102`).

**Rule 6 · long-running work**
- M25 No notification when work finishes, fails or needs input: no toast, no tab-title change, no Notification API (`FE/page.tsx:530-533`).
- M26 No single place for all active and waiting tasks: Jobs & activity and Needs attention cover document and extraction jobs only, not chat answers, goals, onboarding or proposals awaiting confirmation (`FE/jobs-board.tsx`; `FE/needs-attention.tsx:35-55`).

**Rule 7 · starting**
- M27 File limits are not shown before attaching and are wrong: the drag overlay says "PDF, DOCX, TXT, JSON · up to 20 files" and omits spreadsheets and images, which are accepted; the agent's own tool reports the same short list; Quick start shows no size limit and allows 10 files (`FE/agent-v2.tsx:447,581-582`; `AG/agent_tools.py:323`; `FE/quick-start-flow.ts:15`; real list in `BE/file_formats.py:15`).
- M28 Starters and training cards ignore the role: "Add documents" and "Pull out data" are shown to viewers and auditors who cannot do either (`FE/agent-v2.tsx:471-481`; `FE/screens-client.ts:38-45`; `BE/route_policy.py:157,199,247`).
- M29 On phones the document scope cannot be seen or changed: the filter lives in the hidden toolbar and is missing from the options sheet (`FE/phone-design.css:165`; `FE/agent-v2.tsx:445,544-553`).

**Rule 8 · files, tables, charts**
- M30 One bad file rejects the whole selection with only the first reason (`FE/agent-attachments.ts:9-11`).
- M31 Charts: fixed 640×300 viewBox, 11.5 px text (about 6 px on a phone), values only in SVG `<title>` on hover, numbers table collapsed (`FE/answer-chart.tsx:6,28,31,78`; `FE/chat-design.css:119`).
- M32 No upload progress (plain `fetch`, label "Uploading…") and the per-file failure reason is hidden in Details (`FE/page.tsx:407`; `FE/admin-documents.tsx:93,102`).
- M33 The spreadsheet "what was read" report ("Not read: …") goes only into indexed text; no API or screen shows it (`BE/workbook.py:945-950`).

**Rule 9 · permissions**
- M34 Permission denials do not say who can grant access ("This action is not available.", "Administrator access is required."); the agent says only administrators can onboard while the route allows contributors (`BE/route_policy.py:250-254,273-279`; `FE/agent-v2.tsx:308`; `AG/agent_workspace.py:221,229`).

**Rule 10 · phone, tablet, accessibility**
- M35 Agent on a 901–1,100 px touch screen: the phone 760 px cap plus the 240 px rail squeezes the chat to about 520 px with empty bands either side (`FE/phone-design.css:82`; `FE/agent-workspace.css:66`).
- M36 Desktop 1,024–1,499 px: the context panel appears only from 1,500 px and sources open as a modal that covers the conversation; sources are never shown beside the chat at any width (`FE/agent-workspace.css:2,66`; `FE/citation-panel.tsx`, `citation-panel.css:1`).
- M37 More than 25 distinct breakpoints (360, 480, 560, 600, 640/1100, 650, 680, 700, 720, 760, 800, 850, 900, 960, 1000, 1100, 1180, 1200, 1499, 1536, 1600) instead of the three bands; the walkthrough and metadata graph use their own.
- M38 The phone "Chat options" sheet has `role="dialog" aria-modal` but no focus move, trap, Escape or focus return (`FE/agent-v2.tsx:544-553`).
- M39 Screen readers hear nothing when an answer finishes or stops: the only live region is the thinking status, removed at the first token (`FE/agent-v2-chat.tsx:93`; `FE/agent-v2.tsx:466`).
- M40 Tap targets below 44 px in the phone layout: remove-attachment 24 px, remove-filter about 16 px, JSON "Prompt template / Document" choice about 22 px, "View steps" about 20 px, workflow chip 22–24 px, citation chips 28 px, agent chips 36 px, scope chip 40 px, citation tabs 40 px (`FE/agent-v2.css:11,30,33,36,100`; `FE/chat-design.css:131`; `FE/phone-design.css:15,142,162`; `FE/mobile.css:96`; `FE/citation-panel.css:4`).
- M41 Streaming scroll: `scroll-behavior:smooth` plus `scrollTop=scrollHeight` on every update can trip the 64 px "user scrolled up" check during the animation, detaching follow-bottom while reading; the reduced-motion override loses on specificity (`FE/chat-design.css:16`; `FE/agent-v2.tsx:219,466`; `FE/agent-v2.css:20`). Needs a runtime check.
- M42 No dark theme and no token system: no `prefers-color-scheme` or `data-theme`; about 2,750 hard-coded hex values; token files disagree (`readability.css:2` vs `lapi-theme.css:4-5` vs `buttons.css:25`).

**Rule 11 · measurement**
- M43 Nothing is measured. There is no analytics or telemetry in the frontend, no `console` logging, and the backend records only token usage per model call plus `validation.attempts` / `removed_sentences` on each answer. Task success, time to first progress, time to finish, stops, retries, approval rejections, corrections and abandoned tasks are not counted anywhere. Before-and-after results for fixes cannot be reported until this exists.

### Low

- L1 `goalWorkflow` invents a running step "Preparing result answer" while the goal is only queued (`FE/agent-v2.tsx:39`).
- L2 One-step steppers for unknown-length operations: "0 of 1 completed" on database switch and restore (`FE/storage-configuration.tsx:41,77`).
- L3 Phone status shows only the first file's percentage for "Reading 3 files" (`FE/phone-status.tsx:14`).
- L4 Steps land in the wrong phase: "Checking the sources support the answer" under "Write answer"; comparisons and spreadsheet steps under "Understand request" (`FE/agent-answer-workflow.tsx:15-19`).
- L5 Jargon in results: "Updated Parquet is saved. Publishing and verifying vector knowledge…", "N verified vectors", "Write Parquet", raw extraction UUIDs and a JSON dump under "Extracted fields" (`FE/agent-v2.tsx:504-505`; `FE/operation-progress.tsx:8,28,35`; `FE/agent-v2-output.tsx:7,26-29`).
- L6 Unsaved member changes are dropped on close without a prompt (`FE/manage-dataset.tsx:74`).
- L7 History and the Recent rail are disabled while busy (`FE/agent-v2.tsx:451,460`).
- L8 Small confirmation gaps: Active toggle (`FE/manage-dataset.tsx:57`), "Stop using" a model (`FE/model-registration.tsx:101`), consent checkbox names no provider (`FE/admin-documents.tsx:82`), user delete never says whether it can be undone (`FE/user-management.tsx:96`), team delete does not state reversibility (`FE/access-map.tsx:99`).
- L9 Generic server failure text "The answer could not finish. Retry the question." does not say partial text was kept (`AG/agent_workspace.py:669`).
- L10 Reopened chats lose their workflow cards and recovery buttons (`FE/agent-v2-chat.tsx:23`).
- L11 Plan list and "How I read your question" sit above the answer text (`FE/agent-v2-chat.tsx:92-97`).
- L12 Copying an answer drops its sources; Export chat is JSON only and only the last exchange (`FE/agent-v2-chat.tsx:112`; `FE/agent-v2.tsx:497`).
- L13 Tour and training copy do not match the controls: "Tap Add at the bottom", "start with Quick start on your Dashboard" (phones have none), "Tap the paper-clip" (the icon is a plus) (`FE/walkthrough-data.ts:28,35`; `FE/screens-client.ts:40`).
- L14 Quick start rejection notes omit the file name and offer only "Try other files" (`FE/quick-start.tsx:121,254`).
- L15 Extract Data headers use `text-transform:capitalize`, changing field names (`FE/extract-data.css`).
- L16 The support email carries the raw error text and user agent; file search text goes in a query string (`FE/support.ts:8`; `FE/admin-documents.tsx:27`).
- L17 Contrast slightly under 4.5:1 on small agent text: `#567aad` at 11 px, `#647998` at 10–11 px, `#68788e` at 10 px; the copy icon at 55 % opacity never reaches full opacity on touch (`FE/agent-v2.css:10-12,27`; `FE/chat-design.css:58-59,68`).
- L18 Focus: the composer uses `outline:none` with a 1.7:1 border; search inputs on the dashboard and metadata graph have no visible focus (`FE/agent-v2.css:17,92`; `FE/dataset-dashboard.css:36`; `FE/metadata-relationships.css:1`).
- L19 Reduced motion misses `.animate-spin` outside the agent, the skeleton pulse and the training animation (`FE/base.css:442`; `FE/globals.css:701`; `FE/chat-design.css:140`).
- L20 Touch screens wider than 1,100 px keep 32–38 px icon buttons (`FE/buttons.css:13-15`; `FE/chat-design.css:80`).
- L21 Reading column is 768 px with zero answer padding, about 90–95 characters per line (`FE/chat-design.css:6,17,27`).
- L22 Thread `div` has `aria-label` without a role; static `role="status"` notes inside buttons, summaries and every restored message can cause a burst of announcements (`FE/agent-v2.tsx:466,498,504-505`; `FE/agent-answer-workflow.tsx:66`; `FE/agent-v2-output.tsx:16`; `FE/agent-v2-chat.tsx:66,103`).
- L23 `useDevice` initialises during server rendering and listens only to `resize`, so phones get a hydration mismatch and a pointer change is missed (`FE/use-device.ts:7,10`).
- L24 Chip rows use `nowrap` with the scrollbar hidden, so off-screen chips give no hint (`FE/phone-design.css:18`; `FE/mobile.css:42,95`).
- L25 Safe-area insets are used everywhere but there is no `viewport` export with `viewportFit:'cover'`, so on iOS they resolve to 0 (`FE/layout.tsx:15-19`).
- L26 The set-up chat scrolls to the bottom on every line even if the person scrolled up; the whole thread is `aria-live` (`FE/setup-chat.tsx:40,196`).

## 3. Verified as met

- Instant acknowledgement: the question, files and "Submitting request" render before any wait, with a live timer (`FE/agent-v2.tsx:318-320,536-538`).
- Honest progress: upload and extraction bars count completed stages and say so; no timer-driven fake steps anywhere (`FE/batch-progress.tsx:10`; `FE/operation-progress.tsx:24,39`).
- Summary with details on demand: phase chip, then phases, then "Show all N steps" (`FE/agent-answer-workflow.tsx:66-71`).
- Stopped and failed states are named: "Response stopped", "Needs attention", "Stopped · partial answer kept" (`FE/agent-v2-chat.tsx:107`).
- Plans shown and editable before large tasks: the details card, the onboarding form and the batch preview (`FE/agent-v2.tsx:519-529`; `FE/agent-onboarding.tsx:82-110`).
- Destructive actions confirmed with impact and reversibility: file delete (type the name, "cannot be undone"), collection delete (recoverable from Deleted collections), user delete (name plus admin password), embedding Default change ("There is no rollback."), job cancel with a cost warning, Start fresh and Restore (`FE/admin-documents.tsx:74-79`; `FE/dataset-lifecycle.tsx:22-26`; `FE/user-management.tsx:52-53`; `FE/model-registration.tsx:293-308`; `FE/page.tsx:1054`).
- Nothing is marked done before the server answers; instruction changes need the Save button after a before/after view.
- Composer text and files are restored after a failed send and after a clarification (`FE/agent-v2.tsx:360-363,376`).
- Retry from the failed step with per-tool advice; "Check accepted work before resubmitting"; the server refuses a duplicate submission (`FE/agent-v2.tsx:509-516`; `AG/agent_workspace.py:625`).
- Confirmed workflows and goals continue without the browser and survive a reload; past results are reachable from Review, Jobs and Recent chats.
- Citations open the document at the page, or the spreadsheet row with attached and linked rows, and say plainly when no page or quote was recorded (`FE/citation-panel.tsx:58-82`).
- Set-up can be skipped and reopened from About; the tour has Skip; Quick start reopens from the Dashboard, `/Start`, guide chips and a training card.
- Extract Data and chart tables scroll in their own box with sticky headers; results export to Parquet, XLSX, CSV and JSON with review status.
- No `console` logging in the frontend; the Access map explains levels; collection-level denials name who to ask (`BE/dataset_access.py:112`).
- No horizontal page scroll in chat and admin tables (wrapping, `overflow-x` wrappers, `min()`-capped popovers); `dvh` heights; 44 px `.btn` and tab items in the phone layout; the consent dialog is a native `<dialog>` with Escape and focus; the navigation drawer traps focus; the composer is outside the scrolling thread and its Stop is 44 px on phones; main text colours pass 4.5:1.

## 4. Rules or items skipped, and why

- Rule 11 "test on an older phone, a tablet and a slow network": not possible from this machine; see section 5.
- Rule 10 "keyboard not covering the prompt box": the code handles it (tab bar hides, textarea capped to 30 % of `visualViewport`, 16 px inputs) but only a device can confirm it.
- Rule 3 "text in files never treated as permission": proposals always need a confirmation card, but whether document text can steer the model into proposing an action is prompt and guard logic I did not evaluate.
- Rule 9 Keycloak return-to-screen after sign-in: the OIDC start route was not traced.

## 5. Could not verify

- Any rendered layout at 375, 768 or 1,280 px on this machine, because the Next.js dev server cannot start here (missing Windows SWC binary, no npm). Two ways to close this gap: allow installing `@next/swc-win32-x64-msvc` into `lapi_frontend/node_modules`, or point me at the live OCI deployment with a test sign-in.
- Whether the reload race in H2 lands before or after the aborted state is saved.
- Real screen-reader behaviour, iOS keyboard placement, the smooth-scroll race (M41), and contrast over translucent layers.
- Whether the server blocks an owner from removing their own or the last owner's access (M12).

## 6. Proposed fix order (awaiting approval)

Each as its own small change with tests, high first:

1. H1 + H2 + H3: stop and reconnect on the chat path (backend check of the stop flag between steps and saving a finished answer on disconnect; frontend re-attach on reload; Stop/Cancel while busy). This touches agent behaviour, so it needs your explicit approval.
2. H4: Review save vs lock, read-only for viewers.
3. H5: consent before the template helper and the index retry.
4. H6 + H7: show the source-check status and failed lookups next to the answer.
5. H8 + H9: rejected files and unread pages surfaced.
6. H10: table rendering in answers.
7. H11: session-expiry dialog that keeps the draft and the place.
8. H12 + H13: width-based layout; H12 needs your decision because it reverses the v26.1.16.40 choice.
9. M43: a small events table (task started / first progress / finished / failed / stopped / retried / approval rejected / corrected / abandoned) with no content, so later fixes can report before and after.
