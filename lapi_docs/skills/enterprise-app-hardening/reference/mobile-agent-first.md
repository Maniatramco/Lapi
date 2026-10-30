# Agent-first phone version (Lapi v26.1.16.27, "mobile Release 1")

The user's goal: on phones, make the agent the one place to do everything; show only Dashboard, Lapi Agent and
Quick start; let administrators switch any other screen on or off at any time **without a redeploy**, decided
**through OpenFGA** (not a settings page, not Keycloak); administrators always get every screen.

## Screen control
- Model: type `screen`, relation `enabled`, grantable to `user`, `user:*` (wildcard) and `team#member`. Objects
  `screen:<id>` (computer) and `screen:<id>-phone`. Keep `SCREENS` as one list: id, label, frontend views, admin-only.
- Table `screen_grant_tbl(screen, device, grantee_kind everyone|team|user|off, grantee_id)`; no rows = default
  (computer everyone, phone off). An explicit `off` row stops the default coming back. Tuples derive from
  effective grants (`screens.tuples`) inside `authz._desired`; add the model class to `_note_changes` so a save
  resyncs; `_reconcile(user)` must also read `screen:` tuples for that user.
- Answer in one call: `list-objects` type screen for the user (`authz.enabled_screens`); DB fallback without
  OpenFGA. Administrators short-circuit to all.
- API: `GET /api/me/screens?device=phone|computer` → `{screens, views, core, administrator}`; admin
  `GET/PUT /api/screens`, `POST /api/screens/preset`. Route policy + API catalog entries.
- Frontend: pure `screens-client.ts` (`deviceFor`, `viewAllowed`, `agentOnly`); page re-reads every minute and
  when the width crosses 640 px; navigation filters with an `allowed` predicate; a `useEffect` on `view`
  redirects hidden views to Home (covers deep links and saved routes); the phone tab bar drops "More" and the
  shell gets `data-agent-only` to hide the drawer toggle. Hiding is UX only; the route policy still guards the API.
- Admin UI: Access map → Screens tab (grid Phone/Computer, Everyone / Off / one team, presets, save bar).
- Test double: FakeOpenFGA `has()` must honour `user:*` tuples.

## Agent training and Quick start from the agent
- Five cards (`TRAINING_CARDS`, pure), each with a Try it that does something real (set composer text, open
  Quick start). Seen flag like the tour (`/api/me/agent-training`, `TRAINING_VERSION`). Opened by a chip and by
  the Dashboard hero via a window event.
- Chips above the composer: Guided start, Add documents, Pull out data, How the agent works. `/Start` opens the
  Quick start. Quick start's done step: "Continue in Lapi Agent" (select the dataset, navigate).
- Pitfall: the agent component must not import the Dashboard assist bundle (portal, CSS, tour) — the agent unit
  tests compile relative imports for real and 31 of them broke; keep shared openers in a pure module
  (`quick-start-flow.ts`). Wrap `api` calls in effects with `Promise.resolve().then(...)` so a test double that
  returns undefined cannot crash the component.

## Phone design D: answer-first, one-handed (Lapi, after v26.1.16.35)
Designed on a canvas first (six linked 390×844 artboards: Home, Answer, Source sheet, Add, Check the
columns, Review), then built as phone-only CSS plus one component, so desktop is untouched.
- `phone-home.tsx` + `phone-home-data.ts` (pure, unit-tested): greeting by hour, ready count for the chosen
  dataset, one big ask box (questions go to the agent composer, typed in, not sent), suggested questions
  from the newest ready files, "Needs you" from `attentionItems` (opens the shared pop-up), "Reading now"
  with step and share of workflow stages done. Rendered by WorkspaceAssist on Home; CSS hides the old phone
  hero, Quick start banner and floating Ask button with `.phone-home ~` and `body:has(.phone-home)`.
- Tab bar: Home, Ask, a raised dark Add in the middle (opens Quick start), Review (view `Extract`), More.
- `phone-design.css` (loaded after mobile.css, `html body .shell …` specificity): question in a dark
  bubble, answer on a white card, follow-ups and sources as 44px chips, rounded composer; the citation
  `<dialog>` becomes a bottom sheet with a grabber; Quick start mapping is one card per field with a badge
  (`howBadge`: same name / by meaning / linked sheet / AI per row / no column / your choice); Review's save
  footer is sticky with 52px buttons.
- Preview without a backend: build the web image and run it with `API_INTERNAL_URL` pointing at a tiny
  stand-in API (`/api/auth/me` with a csrf token, `/api/datasets`, `/api/documents`, `/api/jobs`, everything
  else `[]`/`{}`), then check at 390px in the browser pane.

## Models on phones (Lapi, after v26.1.16.36)
- Chat model picker on phones: the composer's existing "Agent Model" select gets its own labelled,
  full-width row above the attach/voice/send buttons (phone-design.css). It lists only enabled chat
  models mapped for the dataset and preselects the dataset Default; when none is on it says where an
  administrator turns one on.
- Admin screen "Enabled models" (Manage workspace, all screen sizes; covered by the admin-only `models`
  screen in screens.py): one row per registered model with a 44px switch. Backed by
  `PUT /api/model-registrations/{id}/enabled` (admin in route_policy): writes a new model version with
  only `enabled` changed, no connection re-test; `guard_disable` keeps a workspace Default on (409 with
  the reason, and the UI locks that switch and says which Default to change first). Archived
  registrations are refused.
- Per-device models (after v26.1.16.37): each model stores `devices` (`computer`, `phone`; missing = both),
  set with the same endpoint (`{"enabled": true, "devices": ["phone"]}`; omitted keeps it, empty is 400) and
  kept across connection edits (registration save and `PUT /api/models/{id}` copy it over). `model_public`
  always returns the list. Enabled models shows Phone and Computer toggle chips per model (the last one
  cannot be released: turn the model off instead). `eligibleAgentModels(models, dataset, device)` filters
  Lapi Agent, Dataset Knowledge Chat and Quick start by `useDevice()` (640 px, live on resize), so small
  models serve phones and large ones computers; the dataset Default is used only when it is offered on the
  device, else the first offered model. Like screens, this is a product choice enforced in the app.
- Test harness gotcha: the component tests' stand-in React does not call lazy `useState(() => …)`
  initialisers and finds effects by order or source text; give hooks plain initial values.

## Phones: Agent and Quick Extract only (Lapi, after v26.1.16.38; replaces the phone Home above)
User decision: no Dashboard on phones for anyone, admins included. Phones land on Lapi Agent.
- `phoneRedirect` + `viewAllowed` in screens-client.ts; page.tsx also checks `useDevice()` directly so the
  menu hides Dashboard even before /api/me/screens answers. Review is always allowed on phones because
  Quick Extract hands its result there. Tabs: Agent, Quick Extract (More only when not agent-only).
- Quick Extract = QuickStart with `quickExtract` prop: path preset to extract; the choose step keeps only the
  AI consent and Continue (never drop the consent gate).
- `phone-status.tsx`: one-line attention / reading / extracting rows; the floating progress card is hidden on phones.
- Composer: one row of attach, model name, voice, send; starter chips and footer hide once a conversation exists.
- Review: paging with Previous / Next and swipe (`recordStep`), page scrolls as one, filters hidden. It moves
  between records but there is NO per-record approval in the data model: Reviewed locks the whole run.
- Answers: `citation.reading` is written by query_table from the calculation that ran (`answerReadings`), so
  the headline number and "How I read your question" never rely on the model's wording. A citation with
  `sheet` + `rows` (or section `Sheet: X · row N`) opens Source / Row / Attached / Linked tabs through
  `GET /api/documents/{id}/row-context` (`workbook_context.row_context`, shared with the agent tool).
- Preview tip: to exercise real chat components against a stand-in API, `POST /agent-v2/plans` needs `calls`,
  `document_ids` and `planner`; `/reply` is SSE with `event: done`.

