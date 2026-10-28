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
