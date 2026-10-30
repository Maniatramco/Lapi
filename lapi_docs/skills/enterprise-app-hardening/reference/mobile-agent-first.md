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
