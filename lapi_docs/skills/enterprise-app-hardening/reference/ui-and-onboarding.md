# Screens: Access map, product tour, mobile, shortcuts and onboarding

## Access map (admin; read-only for Auditors) - `access-map.tsx`, `access-map-data.ts`
- Backend `GET /api/access-map` (admin or auditor): users with `levels` (own grants), `effective` (incl. teams),
  `team_ids`, workspace role; datasets; teams; OpenFGA's answer per person (`levels`, administrator, auditor,
  `in_step`) and a `differences` count; `can_edit` false for Auditors.
- Views: **By person / By dataset / By team** SVG graph (center node, lines coloured by level, dashed when it
  comes from a team, orange dashed when unsaved, `!` when OpenFGA differs) and an **Everyone at a glance** grid
  (people and team rows; cells V/E/O, faded when from a team). Clicking cycles
  No access → Viewer → Editor → Owner → No access; one sticky **Save access** bar saves people and team changes.
- Team management: create local teams, edit members (Keycloak teams are read-only: members come from groups),
  delete teams.
- OpenFGA status banner: Off / Down / In step / N differ, with a re-check button.
- Owners (not admins) manage their dataset from Manage dataset → **Members** tab
  (`GET/PUT /api/datasets/{id}/members`, which also returns a people/team directory for the picker).
- Check at desktop and 375 px: the graph scrolls horizontally on phones; the page must not.

## 60-second product tour - `walkthrough.tsx`, `walkthrough-data.ts`, `walkthrough.py`
- Six scenes, about 60 s: Welcome (Connect · Unify · Ask) → Connect sources → Unify (datasets, indexing, OCR,
  model choice) → Ask (answers with sources) → Extract & review → Secure by design (SSO, roles per dataset,
  audit) + "Start on your Dashboard".
- CSS/SVG animation only (transforms/opacity), captions as live text, play/pause, scene steps, keyboard
  (Space, ←/→, Esc), focus trap in the modal, reduced-motion static fallback, works at 375 px.
- Shows once per person after sign-in on the Dashboard; the server remembers it (`GET/POST /api/me/walkthrough`,
  per-user JSON in the control store, `TOUR_VERSION` to show a new tour again). Also in About as
  "Watch the 1-minute tour". It is marked seen when it opens.

### Voice-over (v26.1.16.24) - `useNarration` in `walkthrough.tsx`
- The browser's own **speech synthesis** (no service, no keys, works on phones). Each scene's **caption is its
  voice-over line**, so subtitles always match. `pickVoice()` prefers natural English voices
  (`Natural`/`Neural` > Google > Samantha/Aria/Jenny… > en-US/GB/IN/AU), never non-English.
- Each line must fit its scene: test `wordsPerSecond(scene) <= 2.7`. While a line is still being spoken the
  timeline **holds at the end of the scene** (safety limit scene + 8 s), so words and pictures stay in step.
- Pause cancels speech; resuming with voice on restarts that scene. Voice on/off button, remembered
  (`localStorage` `lapi:tour-voice`).
- **Browsers only speak after a tap.** The automatic first-login tour gets a `not-allowed` speech error → show an
  orange pulsing **"Turn on voice"** button that restarts the scene with narration. Pressing Play works at once.
- Changing the lines = raise `TOUR_VERSION` (frontend and backend) so everyone sees the new tour once.

### Phone and computer versions (v26.1.16.24)
- `SCENES` (computer) and `MOBILE_SCENES` (phone): **same ids and timings**, different lines and titles; the
  phone Connect scene shows "Tap Add → Take a photo or choose files → Merge pages into one". `useDevice()` picks by
  `MOBILE_QUERY = (max-width: 640px)` and follows resizing; every timing helper takes the scene list.
- Computer lines mention Add knowledge connectors, the Lapi Agent, side-by-side Review and the `?` shortcut list;
  phone lines mention the Add tab, photos, merging pages and Quick start.

## Mobile, shortcuts and "ask first, then guide" onboarding (built in Lapi v26.1.16.18-.20)
Design as built (Quick start details: `quick-start.md`):
- **Mobile compact**: every main screen usable at 375 px with no horizontal page scroll, 44 px tap targets,
  a compact top bar, a bottom bar with the 3-4 most used actions (Ask, Add knowledge, Datasets, More), sticky
  primary buttons, collapsible secondary panels.
- **Shortcuts**: keyboard - `/` focus search, `g` then `d`/`a`/`k` go to Dashboard/Agent/Add knowledge,
  `n` new chat, `?` shortcut help dialog; disabled while typing in inputs; mobile - quick-action chips and the
  bottom bar.
- **Onboarding**: after the tour, ask the person (once, server-remembered) **what they want to do** (ask
  questions about documents, extract data, compare/research, build a team knowledge base) and **where their
  knowledge is** (upload files, Google Drive, SharePoint, Amazon S3, Azure Blob, Google Cloud Storage, OCI Object
  Storage). Then drive the next step by their answers **and their access level**: Editors/Owners go straight to
  Add knowledge with that source's step-by-step guide open; Viewers are shown the datasets they can ask; people
  with no access are told how to request it. Dashboard shortcuts follow the saved choices; changeable later.

## Users & passwords additions
Auditor role option and read-only directory for Auditors; "My sessions" and "Authenticator app" cards
(`account-security.tsx`); admin buttons "Sign out everywhere" and "Reset authenticator".

## Renaming a concept people see: "dataset" became "workspace" (Lapi, after v26.1.16.42)
User's words: everyone must understand it, and first sign-in asks them to create one (`first-workspace.tsx`: only when the
list has loaded and nothing is active; Admins and Contributors create, others are told to ask; "Not now" lasts the session).
- Visible text only. Code names, API paths, fields, view ids and old links stay. New hash `#Workspaces`; `#Datasets` still works.
- Reword existing uses of the new word FIRST ("Manage workspace" to "Settings", "workspace Default" to "overall Default").
- Use a syntax-aware script (TypeScript AST, Python ast), not search and replace. Even so, it broke a code key inside a
  cite() argument (`state['dataset']`), which only the full backend suite caught: never rewrite subscript keys.
- Handle the word before punctuation ("datasets."), test regex literals, and text matching on what people type: accept both words.
- Assistant prompts: tools keep saying dataset, so instruct the model to say workspace to people.
- On a shared machine: never `docker ps -q | xargs docker rm`; other projects run there. Filter by your own image or name,
  and cap test runs (`--cpus`, `--memory`, `-n 2`): heavy parallel runs coincided with Docker Desktop failing.
- Who may create (user's rule): any signed-in person, at most one personal and one team workspace; Administrators and
  Contributors have no limit. Enforced in `POST /api/datasets` (409), personal workspaces refuse members (400), the creator
  becomes Owner by updating the grant Lapi already adds on create (adding another breaks the unique key).
  `workspaceSlots` only decides what the screens offer. `migrate-settings` needs Owner on that workspace.

