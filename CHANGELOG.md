# Lapi change history

The application version and in-app feature history are maintained in `lapi_frontend/app/application-version.json`. The About screen and footer read that same file. Entries describe included code; live deployment is recorded separately.

## v26.1.16.39 - 30 October 2026

Phones: Agent and Quick Extract

- No Dashboard on phones for anyone (`phoneRedirect`, `viewAllowed`); phones land on Lapi Agent; Review always allowed on phones. Tabs: Agent, Quick Extract, More when not agent-only. Removes the phone Home and hero.
- `QuickStart` `quickExtract`: extract path preset, consent and Continue in place of the ask-or-extract choice.
- `phone-status.tsx` replaces the floating progress card on phones. Composer is one row; starter chips and footer hide once a conversation exists.
- `query_table` citations carry `sheet`, `rows` and `reading`; `answer-reading.ts` shows the headline number and "How I read your question".
- `workbook_context.row_context`, shared by the agent tool and `GET /api/documents/{id}/row-context`; citation Source, Row, Attached and Linked tabs.
- Review: Previous / Next and swipe through records (`recordStep`), one-page layout on phones.

## v26.1.16.38 - 30 October 2026

Different models for phones and computers

- Models store `devices` (`computer`, `phone`; missing means both). `PUT /api/model-registrations/{id}/enabled` accepts `devices` (omitted keeps it, empty is refused); registration edits and `PUT /api/models/{id}` keep it; `model_public` always returns it.
- Enabled models: Phone and Computer toggles per model; counts of chat models per device.
- `eligibleAgentModels(models, dataset, device)` with `useDevice()` (640 px, live on resize) filters Lapi Agent, Dataset Knowledge Chat and Quick start. Like screens per device, enforced in the app.

## v26.1.16.37 - 30 October 2026

Choose and switch models from a phone

- `PUT /api/model-registrations/{id}/enabled` (administrators): turns a registered model on or off by writing a new model version with only `enabled` changed; `guard_disable` keeps a workspace Default on (409), archived registrations are refused.
- Enabled models screen (`enabled-models.tsx`, Manage workspace, all screen sizes; admin-only `models` screen): one switch per model, uses and Default roles shown, Default switches locked with the reason.
- Phones: the chat composer's Agent Model picker has its own labelled full-width row, with a hint when no chat model is on.

## v26.1.16.36 - 30 October 2026

A phone design that puts the answer first (phones only, up to 640px; computers unchanged)

- `phone-home.tsx`, `phone-home-data.ts`, `phone-home.css`: Home with a greeting, the dataset's ready count, one ask box (questions go to Lapi Agent's composer), suggested questions from the newest ready files, Needs you (from `attentionItems`) and Reading now (step and share of workflow stages done). Replaces the phone hero, Quick start banner, floating Ask button and background progress card on Home.
- Tab bar: Home, Ask, raised Add (Quick start), Review, More.
- `phone-design.css`: chat question bubble and answer card, chip follow-ups and sources, rounded composer; citation panel as a bottom sheet; Quick start column check as cards; sticky Review buttons.
- `howBadge` in `quick-start-flow.ts`: a short badge for each field's column choice, shown in the mapping on every screen size.

## v26.1.16.35 - 29 October 2026

Workbooks: everything read and connected (see `lapi_docs/workbooks.md`)

- `workbook.py`: lists every package part; cells with formulas (pycel for results Excel never saved, `excel_functions.py` for COUNTA/XLOOKUP/XMATCH/TEXTJOIN/DATEDIF/NETWORKDAYS/WORKDAY/SWITCH/PROPER/MEDIAN/STDEV/RANK/COUNTBLANK), classic and threaded comments, hyperlinks, fills and text colours, hidden rows, dropdowns, highlight rules, named ranges; drawings (images via `ocr.read_image` + `ocr.describe`, charts with data from cells when no cache, text boxes, SmartArt), embedded files (OLE unwrapped with olefile), pivots, macros and external links noted; unknown parts reported. Relationships: formula links and per-cell lineage with labels, column formulas, key links between sheets (proven/likely), chart ranges, items linked to rows by anchor and by value, amount agreement. Meaning profiles. Coverage report. Saved as `documents/<id>/workbook.json`; row notes go into the row's text; items, profiles, lineage and coverage become searchable pages.
- `table_extraction.py`: fields mapped by meaning with `providers.plan` over the profiles, checked (column exists, type fits, other sheets only through a key link; exact names win); columns on linked sheets looked up; non-column per-row fields read by the model from each row's own text in budgeted batches; whole-table fields named. `POST /api/templates/table-plan`; `column_mapping` on extractions; Quick start confirmation panel. Workbook field suggestions start from the profiles.
- Chat: `query_table` `join` (same workbook or another spreadsheet), new tools `workbook_map` and `row_context`, and system guidance to map wording to real columns and values and state the mapping and joins.
- `spreadsheet.py`: password-protected workbooks get a clear message. Requirements: pycel 1.0b30, networkx 2.6.3 (also in requirements-local), ruamel.yaml, olefile.

## v26.1.16.34 - 29 October 2026

Spreadsheets are extracted row by row

- `lapi_agent/table_extraction.py`: `plan(schema, documents)` uses the stored tables when every document is a spreadsheet, the prompt is one object of plain values, and at least half of the fields match a column (by key or the label before ':' in the description; exact name first, then a column whose words are inside the field's, longer names first; each column once). `extract` returns `{"records": [{source_filename: "<file> · <sheet> row N", source_key, fields}]}` with values converted to the field type (dates `YYYY-MM-DD`), one evidence quote per row ("Row N") from its search chunk, and a notice listing the mapping and unmatched fields. `schema_for` is the matching records schema.
- `extractor_agent.run`: takes that path before the model graph (stages still reported); sets `table_rows` and `table_notice`; `worker` appends the notice to `evidence_notice`.
- Quick start: `resultRows` unwraps a record's `fields`; `recordCount` shows "record 1 of N". Review groups `table_rows` like merged records and opens on the first row.
- Live cause: a 2,000-row sheet with row fields was sent whole to a cloud model registered with a 32,768-token context and was refused (needed ~69,000).

## v26.1.16.33 - 29 October 2026

Clearer extraction failures in Quick start

- `quick-start-flow.ts`: `extractionStages(status, documents, reached?, error?)` marks a failure on the step it happened in: the furthest status seen while polling, else the step the error names (indexing / worker / recovery → "Waiting for a worker"), else "Reading … with the AI model". `blocked` counts as waiting.
- `quick-start.tsx`: remembers the furthest status (`reached`), shows "The extraction stopped: <reason>" at the top of the Extracting step (the bottom alert is hidden there), and a poll timeout says the extraction is still running ("Still running") instead of "Stopped".

## v26.1.16.32 - 29 October 2026

The tour is a motion video

- `lapi_frontend/public/tour/lapi-tour.mp4` (+ `.vtt` captions, `-poster.jpg`): 1280x720, 30 fps, ~67 s, H.264/AAC. Produced by `lapi_docs/tour-video/` (narration recorded with a neural voice from the scene script, word-timed; an original synthesised music bed; frames drawn with Pillow and timed to the narration; assembled with ffmpeg in a container). See `lapi_docs/tour-video.md` to re-render after a script change.
- `walkthrough.tsx`: `TourVideo` player (play/pause, sound, progress, captions track, end card) used by `Walkthrough` unless `player: "scenes"`, reduced motion, or the video fails to load; the scene player remains as the fallback.

## v26.1.16.31 - 29 October 2026

Skills that apply themselves

- `skills.py`: front matter `document_types`, `domains`, `keywords`, `documents` → `applies_to`; `applies(skill, text, document_names)` returns the reason (word match in the request, document-type or glob match on document names) or ''; `Library.relevant(...)` (at most 4); `render(skill)` writes SKILL.md; `POST /api/skills/upload` (multipart, replaces your skill of the same name), `GET /api/skills/{id}/download`; `SkillInput.applies_to` validated.
- `agentic_chat.system()`: `_auto_skills()` loads matching skills before the answer and adds a "Skills in use (because …)" section; they still only narrow tool access. Built-in `invoice-review` carries applies_to as the example.
- Skills & memory: Upload SKILL.md, "When it applies" fields, chips, Download. Training card "Teach me with a skill" (`TRAINING_VERSION` 2); tour scene "Skills" on both versions (`TOUR_VERSION` 3; 69 seconds).

## v26.1.16.30 - 29 October 2026

The agent guides plain requests end to end

- `agent-guide.ts` (pure): `guideIntent(text)` reads plain words into upload / extract / dataset / prompt / start (commands, `#document` and knowledge questions are left alone); `guideFor(intent, state)` returns the step to show when something is missing (no files → Add documents; no dataset → Choose a dataset / Guided start; no prompt → Guided start / Write a prompt; contributor dataset creation → Guided start) or null; `guidedOperation` maps a ready intent to the deterministic server operation (`agent_operation`), bypassing the model's routing.
- `agent-v2.tsx`: `send()` runs the guide before anything reaches the server; a guided step renders as a Lapi Agent exchange with chips (`runGuide`), the request text stays in the composer; "start" opens the Quick start with the attached documents.
- `openQuickStart(files?)` carries attached documents into the Quick start (`initialFiles`).
- Sign-in artwork (`lapi-banner.tsx`): the "1 CONNECT · 2 UNIFY · 3 ASK" row is gone (the title already says it); the viewBox is cropped to the remaining drawing.

## v26.1.16.29 - 29 October 2026

Dense pages are read in parts

- `ocr.transcribe`: a page is read in parts (up to 8 strips) when its estimated answer would not fit the output budget (`estimate_tokens`, decided before the model is asked) or when the answer still comes back cut off. Cuts land in section gaps (`choose_cut`: a white gap clearly wider than the usual line spacing, nearest the middle), never inside a line or between a table's header and its rows; each lower strip gets the last lines of the strip above (`continuation`) so tables keep their columns. Progress shows why it takes longer ("Page 3 has a lot of text: reading it in parts…", "reading part 2 of 4"). The final error no longer asks people to change `LAPI_OCR_*` settings.
- Deploy: `terraform.tfvars` holds `keycloak_identity_providers`; all three images carry the release tag.

## v26.1.16.28 - 29 October 2026

Sign in with Google

- Hosted deployment: `keycloak_identity_providers = { google = "Google" }` (terraform.tfvars) turns on the Google button; Keycloak's `google` identity provider was already configured.
- Sign-in popup wording never says "Keycloak": "Choose how you want to sign in", "Sign in with Google", "Sign in with a username and password instead", "Emergency administrator sign-in", and plain sign-in error messages.

## v26.1.16.27 - 29 October 2026

Agent-first phone version (mobile Release 1)

- `screens.py` + `screen_grant_tbl`: every non-core screen is an OpenFGA object (`screen:<id>`, `screen:<id>-phone`) with relation `enabled` granted to `user:*`, `team#member` or a person; defaults are computer = everyone, phone = off; administrators always see all. `GET /api/me/screens?device=`, admin `GET/PUT /api/screens`, `POST /api/screens/preset` (`agent-only-phone`, `everything`). Grants sync to OpenFGA with the other tuples (`authz.enabled_screens` list-objects; wildcard type in the model).
- Frontend `screens-client.ts`: device by width (< 640 px = phone), `viewAllowed`, `agentOnly`; `page.tsx` re-reads the state every minute and on device change, hides screens from the navigation (`WorkspaceNavigation allowed`), redirects hidden routes to the Dashboard, hides the phone More menu and drawer toggle when agent-only.
- Access map → Screens tab (`screens-admin.tsx`): Phone / Computer grid (Everyone, Off, one team), presets, save bar.
- Agent training (`agent-training.tsx`, `TRAINING_CARDS`; `GET/POST /api/me/agent-training`): five cards with Try it actions (ask example, open Quick start), shown once per person and from the chip.
- Agent: quick-action chips (Guided start, Add documents, Pull out data, How the agent works), `/Start` opens Quick start (`openQuickStart` now in `quick-start-flow.ts`), Quick start's done step offers "Continue in Lapi Agent" with the dataset selected.
- Phone Dashboard hero "Ask Lapi Agent / How it works" (`workspace-assist.tsx`, `mobile.css`).

## v26.1.16.26 - 29 October 2026

Spreadsheets, exact answers and charts

- `spreadsheet.py` (new; `openpyxl` 3.1.5 + `et-xmlfile` 2.0.0): reads CSV/TSV (encoding fallback, delimiter sniffing) and XLSX (saved formula values, merged cells filled from their first cell, hidden sheets noted, `.xls` refused with advice). Header detection, blank/duplicate column names, per-column types (number incl. "1,234.50" and "(10)", ISO dates, booleans, text). Limits: 50,000 rows, 200 columns, 20 sheets, 2,000 characters per cell.
- Indexing: per sheet a summary chunk (columns, types, counts, ranges, examples) and row chunks packed **only at row boundaries**, each starting with the sheet and its columns and each row written as `Row n · Column: value · …`; rows wider than a chunk are split between column/value pairs. Packing measures with the embedding model's own limit (MiniLM tokens, OpenAI bytes) and those chunks skip the generic re-splitting. Chunks carry `section` ("Sheet: X · rows a-b"), `sheet`, `row_start`, `row_end`, passed through to citations.
- The typed table is stored as Parquet per sheet (`documents/<id>/tables/<n>.parquet` + `tables.json`).
- Upload: XLSX/CSV/TSV accepted, validated fully at upload (renamed files, old `.xls`, empty sheets, limits) with plain messages; spreadsheets are never merged with other files (422).
- Lapi Agent tool `query_table`: validated filters, group by (dates by day/month/quarter/year), count/sum/avg/min/max/count_distinct, row listing, sorting, limits; results cited as "Calculated from <file> · sheet <name>"; optional chart (bar/line/pie/scatter) built from the computed rows and saved on the message as `charts`.
- Frontend: `answer-chart.tsx` / `answer-chart-data.ts` draw the charts in SVG (no new libraries) with a spoken summary, the numbers table and a CSV download (formula-safe). Sources show sheet and rows. File pickers accept spreadsheets.
- Lapi Agent's answer workflow no longer opens its phase panel by itself; a slim status line shows while working.
- Caddy sends `Cache-Control: no-cache` for pages (not `/_next/static` or `/api`), so browsers pick up a new release on the next visit instead of an older cached page.

## v26.1.16.25 - 29 October 2026

Roomier, easier-to-read chat

- `chat-design.css` (imported by `agent-v2-chat.tsx`, so it styles Lapi Agent and the Dashboard chat): 768 px centred reading column; question bubbles; answers without cards in a serif reading stack at 17.5 px / 1.72 (16.5 px on phones); citation pills; code styling; rounded composer with focus ring and orange send button (`--text-input` 16 px keeps the command highlight aligned); calm serif welcome instead of the gradient banner; fade-in for new exchanges; reduced-motion fallbacks.
- Live status line while an answer has no text yet (`chat-phase.ts` `answerPhase`): Thinking → Understanding your question → Searching your knowledge → Writing the answer → Checking the answer against its sources; the empty cursor and token line are hidden meanwhile.
- `AgentAnswerText` renders `- ` / `* ` / `• ` bullets and `1. ` numbered items as list items and blank lines as small gaps.
- Lapi Agent's Context panel shows only at 1500 px and wider (was 1200 px). Phones hide the floating Ask shortcut while the Dashboard chat is open.
- The enterprise-app-hardening skill (all work from v26.1.16.13 on: roles, model Defaults, company sign-in, Quick start, tour voice-over and versions, chat design, deploy routine, pitfalls) is now in the repo at `lapi_docs/skills/`.

## v26.1.16.24 - 29 October 2026

Voice-over and phone and computer versions of the tour

- Two versions: `SCENES` (computer) and `MOBILE_SCENES` (phone), same scene ids and timing; `useDevice` picks by `MOBILE_QUERY` (max-width 640px) and follows resizing. The phone Connect scene shows Tap Add, photo or files, merge pages.

- `walkthrough.tsx` `useNarration`: the browser's speech synthesis speaks each scene's caption when the scene starts (no external service or keys). The timeline holds at the end of a scene until its line has ended (safety limit: scene length + 8 s). Pause cancels speech; resuming with the voice on restarts the scene so words and pictures match.
- Voice on / off control (`localStorage` `lapi:tour-voice`). A speech `not-allowed` error (no user gesture yet, e.g. the automatic first-login tour) shows "Turn on voice", which restarts the scene with narration.
- `walkthrough-data.ts`: captions rewritten as voice-over lines (`wordsPerSecond` keeps each within its scene; tested at 2.7 words/s or less), `pickVoice` prefers natural English voices. `TOUR_VERSION` 2 (frontend and `walkthrough.py`), so everyone sees the narrated tour once.

## v26.1.16.23 - 29 October 2026

Merge files, extraction workflow and Review from Quick start

- Quick start New dataset: name and optional description (`POST /api/datasets` `description`).
- Merge before reading: with 2–20 files, Quick start offers "Merge into one document" or "Keep as separate documents" (photos merge by default; `merge_files=true` on `/api/documents/upload`). Lapi Agent `/Upload` without an extraction step offers the same choice (`extraction_mode=merge` on the plan upload call, which already stitched files). Merged documents are named `merged-<first file>-<n>-files`.
- Extracting: a workflow list from the extraction's real status (`extractionStages` in `quick-start-flow.ts`). Results stay in the popup with Finish and Review; Review dispatches `lapi:open-review` (`OPEN_REVIEW_EVENT`), which `page.tsx` handles with `openReview(id)`.
- Fields step: "Add fields yourself" next to "Suggest fields", for when the model cannot draft them.

## v26.1.16.22 - 29 October 2026

Contributor datasets use the workspace Default models

- `POST /api/datasets/{id}/migrate-settings` gives a new dataset the workspace Default models (empty mappings) when Chat, Extraction and Embedding Defaults are set. Before, it imported the legacy settings as models owned by the caller; for a Contributor those private copies clashed with the Default embedding model ("Datasets use the workspace Default embedding model…"). Without Defaults, non-administrators get 409 asking an administrator to choose them.
- `PUT /api/datasets/{id}/models` and `POST /api/datasets/{id}/local-models` are `admin` again: administrators set the Defaults and do all mapping. Datasets report `chat_choices` (enabled mapped chat models plus the workspace Default chat model), which the chat model pickers use.
- Quick start hides the app-wide "Processing in background" panel while it is open (`quick-start.css`).
- Quick start between 640 and 900 px wide (tablets): its one grid row may now shrink, so the body scrolls and the footer stays visible; before, content past the dialog's max height was clipped. New Enlarge / Smaller button (remembered in `localStorage` as `lapi:quick-start-enlarged`; hidden on phones, where it is already full screen).

## v26.1.16.21 - 29 October 2026

Contributor role from Keycloak

- **`lapi-contributor`** (Keycloak realm role, `LAPI_KEYCLOAK_CONTRIBUTOR_ROLE`): synced at every sign-in and 5-minute re-check into `workspace_contributor_tbl` and the OpenFGA relation `lapi:workspace#contributor`. Contributors are Owner on every dataset (`dataset_access.manages_datasets`) and pass the new `contributor` route policy: creating, deleting and restoring datasets, dataset status and models, assigning documents, dataset onboarding. Workspace management stays `admin`.
- Screens: dataset creation, deletion and model mapping show for contributors; the Access map and Users list label them "Contributor"; `auth/me` returns `is_contributor`.
- To let everyone play around: add `lapi-contributor` to the realm's default roles in Keycloak (`lapi_docs/company-sign-in.md`).

## v26.1.16.20 - 28 October 2026

Quick start and company sign-in

- **Quick start** (`quick-start.tsx`, `quick-start-flow.ts`): one guided workflow, full screen on phones: choose a dataset (administrators can create one with the workspace Default models), add documents (camera or files, up to 10; PDF, Word, text, JSON, images) with consent to process them, live reading progress per file, a first question with suggested questions, the answer and its sources, then next actions (keep asking, add more, share with the team). Viewers choose a dataset and ask. It is the primary next step for everyone (`setup-guide.ts`) and the phone tab bar's Add button.
- **AI-drafted extraction prompts** (`prompt_suggest.py`, `POST /api/templates/suggest`, Editor): the dataset's extraction model reads the start of the ready documents and proposes 4–10 fields (key, label, type, one-line instruction) plus a prompt name; people edit them, or send a requested change with the current fields to have them rewritten. The fields become a strict, nullable JSON Schema template and an ordinary extraction. Needs the same consent as extraction for external models.
- **Quick start** now offers "Ask a question" or "Pull out data" after the documents are read, asks for consent before every AI step (reading documents, answering, extracting), and uses Lapi's look (the sign-in page's blended band and orange primary button).
- **Quick start everywhere**: a permanent launcher at the top of the Dashboard (`workspace-assist.tsx`, `openQuickStart()` event for other screens); on screens 900 px and wider it is a two-column panel with a step rail, on phones a full-screen sheet.
- **Company sign-in providers**: `keycloak_identity_providers` (Terraform) lists Keycloak identity providers (alias → label); Lapi shows one button per provider that passes `kc_idp_hint`, plus "Use a Keycloak account instead". Microsoft, Google and GitHub have their logos. Guide: `lapi_docs/company-sign-in.md`.
- `POST /api/dataset-chat/messages` returns 502 with the reason when the chat model fails, instead of 500.

## v26.1.16.19 - 28 October 2026

Hosted Keycloak starts

- Fix (`keycloak_bootstrap.py`): the platform creates the scratch sub-path `keycloak-secrets` as root, so the api may not change its mode; that `PermissionError` stopped the secrets from being written and Keycloak waited. The folder mode is now best-effort; the secret files stay owner-only.

## v26.1.16.18 - 28 October 2026

Safer sign-in, set-up questions, phones and shortcuts

- **Sessions** (`sessions.py`): 30-minute idle timeout (`LAPI_SESSION_IDLE_MINUTES`) besides the 12-hour limit; `sessions_tbl` gains last activity, address, browser, Keycloak session id and encrypted Keycloak tokens. My sessions (`/api/me/sessions`), sign out others, and administrators' "Sign out everywhere". With HTTPS the cookie is `__Host-lapi_session` (everyone signs in once more after this release).
- **Sign-in limits** (`sign_in_limits.py`, `sign_in_attempt_tbl`): 5 failures per username or 20 per address in 15 minutes lock for 15 minutes, kept in the database with hashed keys; success clears only the username. The client address comes from Caddy's X-Forwarded-For only for requests from this instance. Unknown usernames take the same time as known ones.
- **Authenticator codes** (`totp.py`, `user_totp_tbl`): TOTP for password accounts (break-glass administrators), single-use codes, administrator reset. Password sign-in to an administrator account while Keycloak is on is logged as a break-glass warning.
- **Keycloak**: sessions re-checked every 5 minutes with the refresh token (disabled or signed-out people end, roles and teams follow); back-channel logout `POST /api/auth/keycloak/backchannel-logout`; `id_token_hint` on sign-out; `azp` checked; administrators can be required to have used a second factor (`LAPI_KEYCLOAK_REQUIRE_ADMIN_MFA`, AMR).
- **Hosted Keycloak on OCI** (off: `keycloak_hosted = false`): Keycloak image with the Oracle driver (`lapi_deploy/keycloak`), realm with administrator MFA, brute-force lockout and password policy, `sso.<ip>.sslip.io` through Caddy, `KEYCLOAK` database user created by the api from a Vault secret (`keycloak_bootstrap.py`), PROXY protocol v2 on the load balancer so Lapi sees real addresses.
- **Set-up questions** (`preferences.py`, `setup-guide.ts`, `workspace-assist.tsx`): goals and knowledge sources after the tour, a first step chosen by access level, a "Your next steps" Dashboard card; Add knowledge can open straight into a connector guide (`#Add knowledge/<provider>`).
- **Phones and shortcuts** (`mobile.css`, `shortcuts.ts`): bottom tab bar, floating Ask, 44 px targets, full-screen sheets; `?`, `/`, `g d`/`g a`/`g k`/`g s`/`g u`, `n`, `Esc`.

## v26.1.16.17 - 28 October 2026

Dataset roles, teams, Auditor and a 1-minute tour

- **Dataset levels.** Grants carry a level: Viewer (read and chat), Editor (also upload, reindex, delete documents, prompts, extractions, reviews, connectors, retry or cancel others' jobs) or Owner (also rename, instructions, prompt guide and members). Model mappings, activation and deletion stay administrator-only. The upgrade adds `user_dataset_tbl.access_level` and sets existing grants to `editor`, which is what they could already do.
- **Teams.** New tables `team_tbl`, `team_member_tbl` and `team_dataset_tbl`. Keycloak groups (a `groups` claim from the Group Membership mapper) become teams at each sign-in; local teams are managed in the Access map (`/api/teams`). A person gets the highest of their own and their teams' levels.
- **Owners share datasets** from a Members tab in Manage dataset (`GET`/`PUT /api/datasets/{id}/members`).
- **Auditor** (`workspace_role_tbl`, or Keycloak role `lapi-auditor`): reads Users & passwords and the Access map, no dataset content, no changes.
- **OpenFGA model** now has `dataset` owner ⊃ editor ⊃ viewer, `team#member` grants and `lapi:workspace auditor`; the Access map compares every level with OpenFGA's answer.
- **Route policy.** `route_policy.py` lists every API route and method with who may call it (public, signed in, viewer, editor, owner, audit, admin). Sign-in enforces administrator and auditor routes for every request; dataset levels are enforced by the routes. An unclassified route is refused, and a test fails if any route is missing or stale. This replaces the old path-prefix rule.
- **Product tour.** A 60-second animated walkthrough (Connect, Unify, Ask, Extract and review, Secure by design) opens once on the Dashboard after a person's first sign-in, remembered on the server (`/api/me/walkthrough`), and is in About as "Watch the 1-minute tour".
- Local Keycloak demo (`lapi_local_use/keycloak-demo`) with test users for administrator, user-in-a-group and auditor.

## v26.1.16.16 - 28 October 2026

HTTPS certificate saved for updates

- Caddy now runs as uid 10001 (the api's user). It keeps its files owner-only, so while it ran as root the api could not read them and saved nothing; the folder scan also skipped unreadable folders silently. `tls_state` now logs a warning for a folder it cannot read.

## v26.1.16.15 - 28 October 2026

HTTPS certificate kept across updates

- Fix: `tls_state.keep` compared the folder with itself when its loop started, so a certificate Caddy obtained before then (the first one, in practice) was never saved. It now compares with what was restored from the control bucket.

## v26.1.16.14 - 28 October 2026

Lapi over HTTPS

- On OCI, a Caddy container in the container instance serves Lapi at `https://lapi.<load balancer IP>.sslip.io` (sslip.io turns the IP into a name, so no domain or DNS is needed) with a Let's Encrypt certificate it renews itself. The load balancer passes ports 80 and 443 straight through; port 80 redirects to HTTPS. Set `https = false` in Terraform to go back to plain HTTP, or `https_hostname` to use your own domain.
- The certificate survives deployments: the api saves Caddy's data folder to the control bucket every five minutes when it changes (`tls_state.py`) and restores it before Caddy starts, because Let's Encrypt issues only five certificates a week for one name.
- `COOKIE_SECURE` is on with HTTPS, and `public_url` (and the Keycloak redirect URI) default to the HTTPS address.

## v26.1.16.13 - 28 October 2026

Redesigned sign-in page

- One blended background (deep blue, indigo, rose and peach, with see-through glows and a faint grid) now runs behind the whole sign-in page instead of a white form beside a blue panel.
- The Connect · Unify · Ask diagram (`lapi-banner.tsx`) is unchanged and sits directly on the background under a "Connect. Unify. Ask." headline; the three feature notes under it are removed.
- The sign-in card is frosted glass (blur and a darker tint for readable white text), with an orange Sign in button; Keycloak, administrator sign-in, password reveal, errors, autofill and keyboard focus are restyled for it. The card stays first in reading order and above the diagram on narrow screens; the diagram is hidden below 560 px as before.

## v26.1.16.12 - 28 October 2026

Text-only files are indexed as their text

- New `file_formats.plain_text`: a .pdf, .docx or image file whose contents are UTF-8 text (for example a saved web link) is accepted on upload and cloud import and indexed, chunked and extracted as that text, as one page. Links inside it are never fetched.
- Such a file opens as text from Open original, merges as text rather than as a PDF, and offers no page images.
- Files that are neither the named format nor text (binary data, a renamed image, archive or older .doc) are still refused with what they actually are. A failed document can be indexed again with Retry.

## v26.1.16.11 - 28 October 2026

OCR as a model use with its own Default

- Model Registration: OCR joins Chat, Extraction and Embedding in "Use for", offered for OpenAI (api.openai.com) and Gemini API connections. It shares the model's connection and runs at the Extraction stage with its parameters; it can be combined with Chat and Extraction, never with Embedding.
- Test connection with OCR ticked generates a small image with a known code, sends it through the same OCR path as indexing (Chat Completions or the Responses API, as chosen for the model) and checks the code is read back. A passed image test is saved per connection version (`ocr_test`); editing the connection needs a new test.
- `cloud_ocr.ready`: a model can read images for datasets when it is ticked for OCR with a passed image test, or (as before) is a gpt-4o / gpt-4o-mini or Gemini extraction model. The old gpt-4o-only rule still guards OCR routes that go through an Extraction model.
- Workspace OCR Default (`ocr_model_id` on `lapi_workspace_defaults`, added to existing databases at start-up): set from the Default column in Model Registration; refused until the model's image test passed. Datasets without their own OCR choice use it, then fall back to a vision extraction default. Dataset Model Mapping shows it as the automatic choice and may select it without mapping it.
- Images sent to models other than gpt-4o reserve twice GPT-4o's image tokens when checking the context budget.

## v26.1.16.10 - 28 October 2026

Step-by-step connector guides

- New `lapi_frontend/app/connector-guides.ts`: a plain-language setup guide for every storage connector (Amazon S3, Azure Blob Storage, OCI Object Storage, SharePoint, Google Drive, Google Cloud Storage). Each lists what you need, numbered steps in the provider's console, where each Lapi field's value comes from, and the fix for each error Test connection can return. A shared final part covers Test, Save, selecting files, Vectorize and the OCR model needed for images and scans.
- Add knowledge shows the guide above the connection form, open for a new connection and collapsed when editing a saved one. Text to copy or look for is shown as code.
- The file-selection page lists images among the importable types.
- Test: every provider has a complete guide, and the panel renders.

## v26.1.16.9 - 27 October 2026

Image uploads read with OCR

- PNG, JPG/JPEG and WEBP join PDF, DOCX, TXT and JSON (`file_formats.SUPPORTED`, now the one list used by upload, Lapi Agent and onboarding uploads, merged uploads and cloud connectors). Images are checked by signature like PDF and DOCX; a mislabelled image says what it really is.
- New `ocr.read_image`: refuses images over 50 megapixels before decoding, applies the EXIF orientation, scales the longest side to 2,000 px and sends the image to the dataset's cloud OCR model (the same path as scanned PDF pages: OpenAI gpt-4o / gpt-4o-mini or Gemini; local OCR stays off for dataset jobs). Text is indexed as one page with `text_origin: ocr`, unverified, and cached per OCR model. Blank or unreadable images, OCR turned off and a dataset without an OCR model each fail with a specific reason.
- Merged uploads may include images; they are read in the worker, never on the upload request.
- Images open inline as originals (`/api/documents/{id}/source`, merged sources) and in citations; file pickers and drop zones accept them.
- OCI deployment: `LAPI_OCR_ENABLED=true`, so images and scanned PDF pages are read; nothing is installed or run locally for OCR.

## v26.1.16.8 - 27 October 2026

Clear errors for files that are not really PDF or DOCX

- New `lapi_app/file_formats.py` checks a file's contents against its extension: a PDF must contain the `%PDF-` header in its first 1 KB; a DOCX must be a ZIP with `word/document.xml` and `[Content_Types].xml`. The message names the file and what it actually is: only a web link, a web page, plain text, a renamed DOCX/PDF, an older `.doc`, a different ZIP archive or a damaged file.
- Upload (`/api/documents/upload`), the agent and onboarding uploads and cloud-connector imports refuse such files with that message (400), so no document or indexing job is created. Merged uploads report it per file instead of "Cannot merge these files".
- Indexing reports the same reason for files stored before this check, and a PDF that pypdf cannot open is reported as damaged, instead of "Processing failed; inspect service health and retry". DOCX archive safety checks still run first.

## v26.1.16.7 - 27 October 2026

Google Cloud Storage connector

- New `gcs` source connection (`lapi_app/cloud_sources.py`, `GoogleCloudStorage`): a bucket plus optional folder prefix, read over the Cloud Storage JSON API with a service-account token limited to `devstorage.read_only`. Browsing pages 100 objects at a time with folders; imports pin the selected object generation, so a newer upload is never read under an older selection, and anything outside the prefix is refused.
- Clear errors name what to fix: a missing role asks to grant the service-account email Storage Object Viewer on the bucket; a wrong name reports the bucket was not found.
- The service-account key is checked like Google Drive's (googleapis.com token host only) and stored encrypted; Google Drive and Cloud Storage share the sign-in code.
- Add knowledge offers Google Cloud Storage with bucket, prefix and key fields.

## v26.1.16.6 - 27 October 2026

Local reranker in the cloud deployment

- The API image (`lapi_backend/Dockerfile`) now downloads the pinned local reranker (`cross-encoder/ms-marco-MiniLM-L6-v2`, fixed revision, checked with `verify_assets`) to `/opt/lapi-reranker` at build time and sets `LAPI_RERANK_MODEL_DIR`; build with `INSTALL_RERANKER=false` to leave it out.
- The OCI deployment sets `LAPI_RERANKER=local` for the api and worker containers, so chat and extraction no longer fail with "Chat reranking is unavailable".

## v26.1.16.5 - 27 October 2026

Keycloak sign-in, OpenFGA permissions and multi-use models

- Keycloak (`lapi_app/keycloak_auth.py`): OpenID Connect authorization code flow with PKCE against an existing Keycloak, on when `LAPI_KEYCLOAK_URL`, `LAPI_KEYCLOAK_REALM`, `LAPI_KEYCLOAK_CLIENT_ID` and `LAPI_PUBLIC_URL` are set. State, nonce and verifier travel in an encrypted, ten-minute, `SameSite=Lax` cookie; ID and access tokens are verified against Keycloak's JWKS (issuer, audience/azp, expiry, nonce). Accounts (`kc-<subject>`) are created at the first sign-in, never merged with a local account of the same name, and their role follows the Keycloak role `lapi-administrator` at every sign-in (a change ends older sessions). Sign-out returns Keycloak's end-session URL. Only same-site paths are followed after sign-in. The client secret comes from OCI Vault (`LAPI_KEYCLOAK_CLIENT_SECRET_OCID`) or a mounted file.
- With Keycloak on, password sign-in is refused except for local administrators (break-glass); Keycloak accounts change passwords and roles in Keycloak, administrators add people in Keycloak, and a Keycloak administrator confirms account changes with a sign-in from the last ten minutes instead of a password. The sign-in page shows "Sign in with Keycloak" and folds the password form away.
- OpenFGA (`lapi_app/authz.py`): on when `LAPI_OPENFGA_URL` is set. Administrators (`user:<id> administrator lapi:workspace`) and dataset grants (`user:<id> viewer dataset:<id>`) are tuples; `is_administrator` and dataset access ask OpenFGA, with answers cached per request. The database stays the record: the store is found or created and fully reconciled at start-up and after OpenFGA restarts (in-memory store), and each committed role or grant change is synced. No answer means HTTP 503, never access.
- Terraform: an `openfga` container (v1.22.0, memory store, localhost only, playground off) in the container instance; Keycloak variables, an empty `lapi-keycloak-client-secret` Vault secret readable by the containers, and the `keycloak_redirect_uri` output. The database password secret now also ignores replication settings.
- Model Registration: "Use for" replaces Category. Registrations accept `capabilities` (Chat and Extraction together; Embedding alone), parameters are validated for every use, and an edit may add or remove Chat/Extraction but not cross into Embedding. Ticking Embedding with Chat/Extraction also saves an embedding registration of the same model; Test Connection tests each use.

Validation: full backend suite in parallel, 1,394 passed, 11 skipped, including new `test_keycloak_auth.py` (against a fake Keycloak signing RS256 tokens: sign-in, roles, break-glass, forged state, nonce, signature, replayed code, cancelled sign-in, name conflict, open redirect), `test_openfga_authz.py` (against a fake OpenFGA: decisions, sync, restart rebuild, shared store, stale tuples, refusal when unreachable, batching) and `test_model_uses.py`. The web image build type-checks. Deployed 27 October 2026 with OpenFGA on and Keycloak off; Keycloak was not tried against a real server.

## v26.1.16.4 - 27 October 2026

Choose each model's API

- Setting: model connections gain `chat_api` (`chat_completions` by default, or `responses`). Validation allows Responses for `openai-compatible` and `azure-openai` Chat/Extraction models, without restricting the endpoint host (Test Connection reports a provider that does not support it); other protocols have one chat API, refuse `responses` and store nothing; embeddings ignore it. Existing models keep Chat Completions.
- Translation (`lapi_models/providers/lapi_openai/responses.py`): Lapi keeps building Chat Completions payloads; `request()` turns them into Responses requests (messages and image parts to `input`, tool calls and outputs to `function_call`/`function_call_output`, tools, `tool_choice`, `max_output_tokens`, `reasoning.effort`, `text.format` for JSON schema, `store: false`; `seed`, `stop` and frequency/presence penalties are not sent) and `reply()` turns answers back (text, tool calls, finish reason, usage including cached and reasoning tokens).
- Wiring: `ModelConnection.chat()` picks the API; agent tool steps and answers, `generate()` (chat and extraction) and OpenAI/Gemini OCR use it. A streamed agent answer with Responses is requested once and published in one piece.
- Model Registration: an API field for Chat and Extraction models, with both choices for OpenAI-compatible and Azure OpenAI and the provider's single API (Messages, Converse, generateContent, OCI Generative AI chat, Ollama chat) for the others; the request always sends a value the provider accepts.

Validation: full backend suite in parallel, 1,372 passed, 11 skipped, including new `test_openai_responses_api.py` (request and reply translation, validation per provider, stored setting, an agent tool step with reasoning on `/v1/responses` and on `/v1/chat/completions`, streamed answers in one piece). The web image build type-checks the form; the form was not previewed in a browser.

## v26.1.16.3 - 27 October 2026

Model tests explain provider errors

`ModelConnection.post` (`lapi_models/connection.py`) used to report only the HTTP status of a failed model request, so a Test Connection failure such as OpenAI's HTTP 400 gave no hint of the cause. `provider_reason()` now extracts the provider's message (OpenAI/Anthropic `error.message`, or `message`/`detail`), on one line, at most 300 characters, with the request's credentials and anything key-like (`sk-…`, `Bearer …`, long tokens) replaced by `[redacted]`. It is added only inside `explaining_provider_errors()`, which the Model Registration test endpoint uses: its requests are synthetic. Every other model call keeps the status-only message, because provider error bodies can echo prompts and document text.

Validation: full backend suite in parallel, 1,361 passed, 11 skipped, including new `test_model_error_reason.py` (OpenAI and Anthropic formats, key redaction, missing reasons, reason shown only while testing a registration) and the existing no-echo tests in `test_anthropic_chat.py`.

## v26.1.16.2 - 27 October 2026

A redesigned sign-in page

- Layout (`sign-in-layout.tsx`, new `login.css` loaded last): a white form column first in reading order, then a brand-blue story panel. The panel carries the message as real text ("Ask your data. Get answers you can trust." and one sentence on what Lapi does), the diagram, and three facts (cited answers, governed access, self-hosted). The rotating "Built for" ticker is replaced by a quiet "Secure sign-in. Sessions end after 12 hours." line, matching the 12-hour session cookie.
- Diagram (`lapi-banner.tsx`): redrawn for the blue panel in a 1200x580 space without the headline text it used to embed: glass source tiles, a white knowledge core with the Lapi mark, orange ring and orbit, and a Lapi Agent chat card (dark header with the Lapi mark, question bubble, answer with numbered citations, matching numbered source chips, "Verified against your data").
- Form: larger 50px fields with a focus ring, a gradient Sign in button, left-aligned heading and copy. The existing `.login-card`, `.login-story`, brand-name/tagline and accessibility labels are kept for the tests.
- Responsive: two columns from 961px; below that the form comes first and the panel follows; the facts stack below 641px; the diagram is hidden below 561px, where its labels would be under 6px.
- `login.css` overrides the earlier sign-in layers (`readability.css`, `sign-in.css`, `lapi-theme.css`) instead of editing them; their pillar, glow and illustration rules no longer match any sign-in markup.

Validation: rendered from the actual `sign-in-layout.tsx` and `lapi-banner.tsx` with all 13 application stylesheets in `layout.tsx` order (React 18.3.1 and Babel in a browser preview) at 1440x900, 1100x720, 820x1000, 375x812 and 320x900: no horizontal scrolling, form above the panel below 961px, headline 34px at 1100px, the 1100x720 panel fits the window. lucide-react 0.468.0 provides Lock, Quote, Server and ShieldCheck. The frontend type-check, unit and browser tests were not run (no Node.js on this computer).

## v26.1.16.1 - 27 October 2026

Oracle vector table at start-up; sign-in over HTTP

`core.init()` now calls `prepare_vectors()` inside the existing schema lock: when the engine is Oracle and `SEARCH_PROVIDER` is `oracle`, it runs `oracle_vectors.prepare()`, which creates `lapi_knowledge_vectors` and its index if missing. Before, only activating Oracle on the Storage > Database screen created that table, so the container deployment (Oracle configured through environment variables) answered `/ready` with 503 and its api container was restarted by its health check about every 3–4 minutes; indexing and chat would also have failed.

Sign-in over HTTP: browsers only provide `crypto.randomUUID` on secure pages (HTTPS or localhost), so on the plain-HTTP deployment every API call failed after sign-in with "crypto.randomUUID is not a function". A new `randomId()` helper (`lapi_frontend/app/random-id.ts`) uses `crypto.randomUUID` when present and otherwise builds a version-4 ID from `crypto.getRandomValues`; `page.tsx`, `admin-documents.tsx`, `agent-onboarding.tsx` and `re-extract.tsx` use it.

Validation: full backend suite in parallel, 1,357 passed, 11 skipped, including new tests for when the table is prepared and that start-up calls it. The ID fallback was run on the live plain-HTTP page (not a secure context, `crypto.randomUUID` undefined): 500 unique, valid version-4 IDs. New unit test `lapi_testing/frontend/random-id.test.cjs`; the frontend unit tests and type-check were not run (no Node.js on this computer).

## v26.1.16.0 - 27 October 2026

Containers on OCI, no setup token

- First administrator: the public `POST /api/auth/setup` endpoint, the sign-in setup form and `LAPI_BOOTSTRAP_TOKEN` are removed from the backend, frontend, `.env` templates, Compose, Kubernetes and setup scripts. `python -m lapi_app.create_admin` (wrapped by `create-admin.sh`/`.ps1`) creates the first administrator from stdin and refuses once any account exists; on hosts without a shell the api creates it once at start-up from `LAPI_FIRST_ADMIN_USERNAME` and an OCI Vault secret.
- OCI Vault: `core.secret_cipher()` reads its master key from the Vault secret in `LAPI_MASTER_KEY_SECRET_OCID` (instance or resource principal) when set; `LAPI_MASTER_KEY` still works locally; both together are refused. `python -m lapi_app.vault_master_key store|check` moves an existing key into Vault. Oracle connects with a TLS connect descriptor (`ORACLE_DSN`) and a password from Vault (`ORACLE_PASSWORD_SECRET_OCID`).
- Stateless containers: `core.local_store` (settings, encrypted credentials, model registrations, storage routes, knowledge manifests, workspace archives) can be an Object Storage prefix (`LAPI_CONTROL_STORE=oci`); the default remains the local disk. `core.scratch` keeps only file locks and the object cache. Directory listings use `core.files_in`, control keys route to the control store, and workspace reset archives, clears and restores through stores with the same archive layout and checksums.
- Deployment: `lapi_deploy/lapi_containers` (Terraform) provisions the VCN (public load-balancer subnet, private container subnet with NAT and service gateways), a 10 Mbps load balancer, the documents/control bucket, Vault secrets, OCIR repositories, IAM for the containers' resource principal, and one container instance running web, api, worker and Ollama (`qwen3:4b`, `nomic-embed-text`), reading the existing `lapidb`. `push-images.ps1` builds and pushes the images. `lapi_deploy/lapi_oci` (VM with bootstrap token) moves to `delete/`.
- Tests: the backend suite runs in parallel (pytest-xdist, per-worker storage and SQLite via `lapi_testing/backend/conftest.py`, shorter temp paths for Windows) in about 4 minutes instead of about 30; `-n 0` runs serially.

Validation: the full backend suite passed in parallel (1,355 passed, 11 skipped), including tests for create-admin, the removed setup endpoint, the Vault master key and database password, one-time first-admin creation and the Object Storage control store. `terraform validate` passed. Ported from the same changes developed and deployed on the earlier `remove-bootstrap-token` branch; frontend type-check and browser tests not run (no Node.js on this computer).

## v26.1.15.0 - 27 October 2026

One knowledge base

- All datasets now share one knowledge index built with the workspace Default embedding model: each document is embedded once, and the index catalog lives in the database instead of files on one server.
- Model Registration marks one Default model per role (Chat, Extraction, Embedding). Datasets use the workspace Default unless they choose their own Chat or Extraction model; only models with a passing connection test can become Default.
- Changing the Embedding Default asks for explicit confirmation, deletes the knowledge index straight away and rebuilds it; a banner on every page shows how many documents are reindexed and lets administrators retry failures. Chat answers from documents already reindexed and says the index is still building.
- When existing datasets use different embedding models, an administrator chooses one Default before the shared index is built.

## v26.1.14.0 - 27 October 2026

Agentic chat, skills and memory

- Lapi Agent can run as an agentic chat (LAPI_CHAT_MODE router, agentic or auto). With a cloud function-calling model such as Gemini it plans, calls several read tools in parallel, reads more evidence per step and answers in one loop; the local model keeps the routed chat.
- Every factual sentence must cite a source read for this answer, and its numbers, dates and names must appear in that source. A failing answer is revised once; anything still unsupported is removed and the answer says how many statements were removed.
- Follow-up questions understand earlier turns (text and citation IDs only), and answers show the agent's plan, source snippets and up to three suggested follow-up questions.
- New Skills & memory page: built-in and custom skills (/skill), dataset answer instructions with versions (/instructions, /optimize with a Save card), model prompting guides, and a private memory note with 90-day question history that you can edit, switch off or clear.
- Token usage is recorded for every model call with dated prices per model; each answer shows its tokens and approximate cost per step, and administrators get a Token usage report with CSV export.
- Model Registration has a typed parameter form per stage (Chat answer, Tool steps, Extraction, Optimize) with documented Lapi defaults, suggested values, per-stage test prompts and a change history.
- Claude and Bedrock prompt caching and an OpenAI prompt cache key keep the stable agent instructions cached between turns.

## v26.1.13.6 - 27 October 2026

Connect · Unify · Ask

- The Lapi tagline is now Connect · Unify · Ask: the banner's middle step reads Unify, and the sign-in card uses the same tagline.
- The sign-in form no longer sits in a card: it blends into a light page background that is cleaner behind the form and softly tinted blue and orange at the edges.

## v26.1.13.5 - 27 October 2026

Horizontal sign-in banner

- The sign-in banner now flows left to right: data sources on the left, the knowledge core in the middle and a cited answer on the right.
- The Lapi mark sits at the centre of the knowledge core, circled by a slowly turning ring of vector points; the banner is wider and landscape.

## v26.1.13.4 - 27 October 2026

Lapi brand

- New Lapi brand: an L with a speech-bubble P (ask) and an orange answer dot, from Laya (harmony) and Poorni (complete).
- The mark on white is used in the header, sign-in card and banner; the blue-tile version is the Lapi Agent icon, browser tab icon and app icon.
- A custom lowercase lapi wordmark, with an orange dot on the i, leads the sign-in banner.

Assets: `lapi_frontend/public/lapi-mark.svg`, `lapi-agent.svg`, `lapi-wordmark.svg`, `lapi-wordmark-white.svg`, `lapi-mark-180.png`, `lapi-mark-512.png` and `favicon.ico`.

## v26.1.13.3 - 27 October 2026

Lapi LP monogram

- New Lapi LP monogram: the L and P share one stem, with a white L foot, a light-orange P bowl and a knowledge node, on a blue tile.
- The monogram is the Lapi Agent icon everywhere (chat, workflow tracks, activity capsule) and is used in the header, sign-in card, password recovery, the sign-in banner and the browser tab icon.

The mark is `lapi_frontend/public/lapi-mark.svg` (PNG copies at 180 and 512 px); the previous shield image was moved to `delete/`.

## v26.1.13.2 - 27 October 2026

Connect · Vectorize · Ask sign-in banner

- The sign-in banner tells the Lapi story in three steps: Connect data from anywhere (documents, databases, cloud storage, apps and APIs, sheets, email), Vectorize it into one unified knowledge base, and Ask questions that come back with sources.
- The banner is drawn in the Lapi palette with flowing blue and orange dots, scales sharply on every screen, and pauses its motion when reduced motion is requested.
- The sign-in tagline is now Connect · Vectorize · Ask.

The banner is the `LapiBanner` SVG component in `lapi_frontend/app/lapi-banner.tsx`; the previous raster banner was moved to `delete/`.

## v26.1.13.1 - 27 October 2026

Lapi colours: white, blue and light orange

- Every screen uses the Lapi palette: white surfaces, blue for primary actions and headers, and light orange accents.
- The sidebar is white with a blue selected item and an orange marker; page headers, workflow tracks and the Agent progress capsule use one blue band with a warm orange glow.
- The sign-in page is light, with the banner shown as a framed card beside a white form.

Colours are defined once in `lapi_frontend/app/lapi-theme.css`; remaining navy fills elsewhere were mapped to the blue scale.

## v26.1.13.0 - 27 October 2026

Lapi: new name and separate deployment

- The application is now Lapi: sign-in page, logo, header, Agent, About, code folders, Python packages, settings and environment names all use Lapi.
- Lapi runs on its own Always Free OCI resources: a dedicated compartment, network, server and Autonomous Database.

Code, folders and settings were renamed: `lapi_*` folders, the `lapi_app` Python package, `LAPI_` settings, the `lapi_session` cookie, the `LAPI_OWNER` database owner and the `lapi_items` records table. `lapi_deploy/lapi_oci/` provisions and deploys the Always Free OCI environment.

## v26.1.12.18 - 26 October 2026

One workflow track everywhere

- Every workflow uses the navy phase track: Agent onboarding, tool steps and prompt progress, uploads, extraction and document processing, Files & processing, and storage and connection operations.
- Each step keeps its name and status visible, finished steps fill the line, dots flow into the running step and the running step carries the Lapi shield; phones show a vertical list.

## v26.1.12.17 - 26 October 2026

Agent workflow and dataset editing

- While Lapi Agent works, a navy capsule shows the Lapi shield in a spinning ring with the current step, such as Searching knowledge or Writing the answer.
- The answer workflow groups its steps into four phases: Understand request, Find evidence, Write answer and Check & save. It opens inline under the agent header as a navy phase track with the agent shield on the live phase; Show all steps keeps every actual step and its timing.
- Edit any dataset from Datasets, or type /Manage in Lapi Agent: rename it, change its description or active state, its models, documents and prompts. In the Agent the dataset card stays in the conversation, and Upload or Extract start /Upload or /Extract there.
- Administrators can rename and describe datasets without changing their models, documents, prompts or access.

## v26.1.12.16 - 26 October 2026

Jobs monitoring

- Jobs & activity becomes a monitoring view: running and queued work, failures that need attention, jobs completed in the last 24 hours and the average time per completed job.
- Each job shows who started it, its dataset, when it started, how long it took and its progress. Administrators see usernames; other users see You or Another user.
- Activity by person shows each person's running, failed and completed jobs; select a person, job type or search text to filter the list.

## v26.1.12.15 - 26 October 2026

Redesigned workspace screens

- Lapi Agent opens as a workspace: a conversation rail with recent chats, a wider thread and a context panel, with workflow cards to start Onboard, Upload, Extract or Re-extract.
- Agent commands now start with / (/Onboard, /Upload, /Extract, /ReExtract); a leading @ is still understood. While work runs, the agent icon shows the live step: searching, reranking, writing, checking citations, uploading, indexing or extracting.
- Every workspace screen opens with a brand page band and summary counts: Dataset, Prompt, Extract, Review, Jobs (now status tabs and cards), Model Registration, Model Mapping (with a dataset quick-pick that names missing models), Users and Files & processing.
- Click any Need attention count or failed status to open a pop-up listing each affected file with its processing stages, the stored error, what to do next, Retry and links to the screen that fixes it. Administrator-only fixes tell other users to ask an administrator.
- Buttons follow one compact standard across the workspace: the same size and shape, a brand-blue primary action, white secondary actions and red-outlined delete. New extraction moves from the top bar into the Extract and Review pages.
- About shows the current version, a worked example from predefined prompts to reviewed fields and the golden copy, and a collapsible version history.

## v26.1.12.14 - 26 October 2026

Dashboard landing and Add knowledge

- Open Dashboard on a brand overview: greeting, an Ask box, summary counts from loaded accessible records, dataset cards and Sources. Asking gives the chat the full page; Back to overview keeps the conversation.
- Quickly add or remove datasets from the Ask box, and choose individual files in a redesigned Add Dataset Knowledge picker. New knowledge in chat is announced with suggested questions; nothing runs until you ask.
- Add new knowledge: any signed-in user can connect Amazon S3, Azure Blob Storage, OCI Object Storage, SharePoint or Google Drive to a dataset they can access, test it, browse and Vectorize up to 20 files. Connections are private to their owner; administrators see all.
- Vectorize indexes copies with the dataset embedding model and publishes them to chat before showing Ready to ask. Extraction and review stay separate. Credentials are encrypted and never shown again; wrong details get specific guidance.
- Read-only snapshots: cloud files are never changed, and later remote changes, deletions and permissions are not synchronized.

## v26.1.12.13 - 26 October 2026

Animated sign-in

- Show the unchanged Lapi banner on its own edge navy, with dots that travel along the banner's model and knowledge-source connector lines into the shield.
- Blend the sign-in side from navy into blue and violet with a slow horizontal shift, drifting cyan and violet light and a frosted form card showing the Lapi shield, name and tagline.
- Rotate the banner's five platform pillars beneath the form. All motion is horizontal and stops when the device requests reduced motion.
- Place the sign-in form before the artwork in reading order and on mobile. Labels, autocomplete, focus, password visibility, recovery and authentication behavior are unchanged.

## v26.1.12.12 - 24 October 2026

Reliable file catalog refresh

- Show saved indexing and model mapping status without contacting model services while listing files.
- Keep a slow file-list response visible by preventing overlapping timed refreshes.
- Keep live model validation on retry and extraction submissions, and preserve complete document cleanup.

## v26.1.12.11 - 24 October 2026

Admin files and processing

- List application source files and their OCI/local storage, indexing, OCR and extraction status under Manage workspace.
- Retry indexing and start new extractions with current dataset model mappings.
- Preview permanent document deletion and remove related originals, revisions, OCR, indexes, result files and affected chats/workflows with resumable cleanup.
- Include visible Save and New extraction buttons from the preceding prepared release.

## v26.1.12.10 - 24 October 2026

Visible extraction and Save actions

- Start a new extraction directly from the Extract screen with a labeled button.
- Keep New extraction text visible on Review and on small screens.
- Show labeled Save buttons in Model Mapping, model registration and settings instead of tick-only controls.

## v26.1.12.9 - 24 October 2026

Rerun with current mapped models

- Resolve current dataset models for each new Re-extract, prompt Resume and Reindex submission.
- Rebuild scanned source indexes when the mapped OCR model changes before Review re-extraction.
- Prevent historical retries from replaying outdated model mappings or damaging successful indexes/results.
- Keep accepted jobs pinned and preserve earlier results and original files.

## v26.1.12.8 - 24 October 2026

Cloud OCR page budgets

- Use the selected OpenAI model's registered context limit for OCR.
- Estimate GPT-4o and GPT-4o Mini image tokens with their cloud tile rules, preserving original pixels.
- Keep cloud-only OCR selection and reject pages that exceed the registered model budget before inference.

## v26.1.12.7 - 24 October 2026

Cloud-only dataset OCR

- Offer only compatible OpenAI and Gemini OCR models in dataset Model Mapping.
- Automatic OCR uses the compatible cloud extraction default, with no local model fallback.
- Reject local OCR selections and give a clear cloud model selection message when scanned content needs OCR.

## v26.1.12.6 - 24 October 2026

Choose OCR per dataset

- Choose a compatible OpenAI or Gemini OCR model independently in Model Mapping, alongside Embedding, Chat and Extraction.
- Keep Automatic provider routing or explicitly use the configured local OCR service.
- Apply the choice to new indexing jobs, retain queued work and embedding settings, and reindex existing documents to read their images again.

## v26.1.12.5 - 24 October 2026

OpenAI OCR for cloud datasets

- Read scanned PDF pages and embedded Word images with the mapped GPT-4o or GPT-4o Mini extraction model.
- Disclose OpenAI image transmission and pin the saved model and credential version for each job.
- Keep embeddings separate, retain original documents and transcription checks, and report cloud failures without falling back to local Ollama.

## v26.1.12.4 - 24 October 2026

Summarize selected dataset knowledge

- Treat broad knowledge-base summaries as complete read-only questions scoped to the selected dataset or documents.
- Route short summaries through the model instead of assuming a previous extraction answer.
- Preserve hybrid retrieval, reranking, evidence citations and separate processing confirmations.

## v26.1.12.3 - 24 October 2026

Multiple models per dataset

- Enable several Chat and Extraction models per dataset while retaining one default for each role.
- Keep enabled alternatives when a default changes; protect selected defaults from being disabled.
- Preserve embedding selection, index generation and existing mapping concurrency checks.

## v26.1.12.2 - 23 October 2026

Reliable Agent source routing

- Use strict OpenAI and Azure routing arguments, with nullable optional values normalized before canonical validation.
- Separate original document questions, semantic search and saved extraction filters so content questions retrieve indexed passages.
- Keep dataset/topic names out of filename filters, preserve selected access scope, and retain hybrid search, reranking and citation validation.

## v26.1.12.1 - 23 October 2026

OpenAI Agent routing compatibility

- Fix OpenAI and Azure OpenAI Agent routing by declaring each route alternative as an object-shaped function.
- Validate returned arguments against the selected branch and canonical route, and retain provider function names when continuing a tool conversation.
- Preserve dataset access, hybrid retrieval, reranking, cited answer validation and existing model registrations.

## v26.1.12.0 - 23 October 2026

Direct Claude for Agent chat

- Register a direct Anthropic Claude Chat model using its API key, exact model ID and optional workspace ID.
- Test native function calling before saving, map the model to datasets and select it for Agent or Dataset Knowledge Chat.
- Preserve scoped knowledge retrieval, reranking, citation checks and existing Embedding, Extraction and processing models.

## v26.1.11.0 - 23 October 2026

A roomier three-panel Dashboard

- Arrange authorized datasets on the left, Dataset Knowledge Chat in the centre and Sources on the right.
- Keep dataset and source panels visible when selecting knowledge; expand chat only when requested.
- Use separate Datasets, Knowledge Chat and Sources views on smaller screens while preserving the conversation and draft.

## v26.1.10.3 - 23 October 2026

Restore the light sign-in background

- Keep the sign-in page white-toned with subtle blue and cyan background accents matching the supplied banner.
- Preserve the banner image, removed duplicate sign-in branding and supplied shield throughout the application.

## v26.1.10.2 - 23 October 2026

Use the supplied shield for Lapi Agent

- Use the supplied Lapi shield wherever the shared Agent identity appears: navigation, welcome screens, chat replies, workflow guidance and the floating shortcut.
- Archive the previous Agent artwork; preserve existing icon sizes, accessible labels, chat behavior and workflow status icons.

## v26.1.10.1 - 23 October 2026

A blended sign-in background

- Remove the repeated Lapi logo and tagline above the sign-in heading.
- Match the sign-in page background to the supplied bannerâ€™s navy tones without changing, cropping, fading or blending the banner image.

## v26.1.10.0 - 23 October 2026

Lapi platform branding

- Use the supplied Lapi shield logo in the sign-in page, workspace header, navigation, password recovery and browser icon.
- Display the supplied platform banner in full beside sign-in on desktop and below the form on mobile.
- Archive the previous artwork and keep this frontend branding change independently reversible in Git.

## v26.1.9.1 - 21 October 2026

A cleaner Dataset Knowledge Chat input

- Remove the inner rectangular border, focus outline and background from the Dashboard chat input.
- Keep the rounded outer composer focus indicator and existing keyboard, draft and chat behavior.

## v26.1.9.0 - 19 October 2026

Explore metadata as a connected graph

- Explore records and expand or collapse their saved connections in place, using the existing access-scoped metadata API.
- Arrange the graph as a network or lineage; pin nodes to preserve their positions during automatic layout.
- Highlight neighbouring records, filter entity types, toggle relationship labels, zoom with the wheel and inspect parallel links separately.
- Keep mouse, touch and keyboard node movement, scoped counts and read-only processing boundaries. No Neo4j service or paid cloud feature is required.

## v26.1.8.0 - 19 October 2026

Arrange metadata relationship nodes

- Drag each category or record node independently with a mouse, touch or pen; connections and labels follow its position.
- Pan the background, zoom, fit the arranged graph to the screen or restore its starting layout with the reset icon.
- Use arrow keys to adjust a focused node, Shift for larger steps and Home to reset that node. Enter or Space opens its details.
- Keep separate arrangements for scoped desktop and mobile views while the explorer is open, including across list switches and refresh. No metadata or model calls are changed.

## v26.1.2.2 - 19 October 2026

Compact chat layout controls

- Use icons for showing or hiding Sources and expanding or restoring the Dashboard chat layout.
- Keep descriptive tooltips, accessible labels and larger mobile touch targets for the layout controls.
- Preserve the selected knowledge, draft and conversation when changing the layout.

## v26.1.2.1 - 19 October 2026

Give Dataset Knowledge Chat more room

- Expand Dataset Knowledge Chat after indexed knowledge is included through the picker, dataset cards, checkboxes or drag and drop.
- Collapse dataset cards, Sources and guidance around the conversation. Keep the knowledge summary and Add Dataset Knowledge available.
- Inspect sources or restore the Dashboard without resetting the chat draft, selected knowledge or conversation. Focus the composer when chat opens; send no question automatically.
- Fit the expanded conversation and composer within the desktop and mobile workspace.

## v26.1.2.0 - 18 October 2026

Explore metadata relationships

- Open Metadata Relationships from the Dashboard Knowledge Source header, on demand.
- Explore access-scoped datasets, documents, saved extraction runs, prompt versions, review revisions and mapped models.
- Inspect records and relationships with dataset selection, search, graph/list views, zoom, pan and mobile details.
- Lapi blue and navy relationship graph on a light canvas, with matching controls and record details.
- Read-only metadata inspection preserves Dashboard chat and processing workflows; no model calls, graph database or schema changes are required.

## v26.1.1.0 - 17 October 2026

Dataset knowledge, within easy reach

- Add Dataset Knowledge stays visible in a sticky toolbar while sources and chat scroll, including when Sources is collapsed.
- Combine multiple datasets using the Include dataset checkboxes or the indexed-file picker.
- Drag dataset cards into Sources to include their accessible indexed files, preserving other selected sources.
- Find the current version and version-by-version feature history on the About screen.

## v26.1.0.0 - 17 October 2026

Lapi baseline and Dashboard foundation

- Document onboarding, uploads, model mappings, extraction, review and the original Lapi Agent.
- Dashboard with dataset cards, permitted Unified Knowledge sources and a separate read-only Dataset Knowledge Chat.
- Chat opens on demand. Greetings and self-contained general questions use the selected model without knowledge lookup; dataset questions retain retrieval, reranking and citations.
- Compact Connections footer with model hosting details. Original Dataset onboarding remains in its existing workspace.
