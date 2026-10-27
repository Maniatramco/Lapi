# Lapi change history

The application version and in-app feature history are maintained in `lapi_frontend/app/application-version.json`. The About screen and footer read that same file. Entries describe included code; live deployment is recorded separately.

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
