---
name: enterprise-app-hardening
description: Make a FastAPI + Next.js web app enterprise-grade the way Lapi was done - HTTPS with Caddy + sslip.io and certificate persistence, hosted Keycloak SSO (groups to teams, administrator / contributor / auditor roles, company sign-in buttons for Microsoft/Google/GitHub, session re-checks, back-channel logout), OpenFGA authorization with Viewer/Editor/Owner levels and teams, a per-route access policy enforced centrally, admin-only model defaults and mapping, session hardening (idle timeout, My sessions, __Host- cookie), sign-in limits, TOTP for break-glass admins, an Access map screen, a narrated 60-second product tour with phone and computer versions, a guided Quick start (phone and web) with merge-files, AI-drafted extraction prompts and Review hand-off, a roomy Claude-style chat layout, and Excel/CSV support with row-aware indexing, exact table answers and charts. Use when the user asks to "do the same for Aegis" (or another app), to add Keycloak or OpenFGA, roles and teams, HTTPS on OCI, onboarding/Quick start, the tour, the chat redesign, or asks how Lapi did any of these.
---

# Enterprise app hardening (the Lapi playbook)

This skill records what was built for **Lapi** (`C:\Users\Laya\Documents\Lapi`) so it can be repeated in
**Aegis** (`C:\Users\Laya\Documents\Codex\2026-10-25\task-3\aegis-sprint2`) or another FastAPI + Next.js app.
Copy patterns from the Lapi files named below; adapt names (`lapi_` → `ags_`), do not copy blindly.
A copy of this skill is committed in the Lapi repo at `lapi_docs/skills/enterprise-app-hardening/` — keep both in step.

Reference files in this folder:
- `reference/checklist.md`: the verification and deploy-safety checklist (use it every phase).
- `reference/https-caddy-sslip.md`: HTTPS on an OCI load balancer with Caddy, sslip.io and saved certificates.
- `reference/openfga-model.json`: the OpenFGA authorization model.
- `reference/route-policy.md`: the access levels (incl. Contributor), what each allows, and the route-policy pattern.
- `reference/keycloak-realm.md`: Keycloak realm, client, mappers, MFA flow, and Lapi's OIDC handling.
- `reference/company-sign-in.md`: Microsoft/Google/GitHub buttons via Keycloak identity providers, and the
  Keycloak problems we hit in production with their fixes (incl. the Identity Provider Redirector step and
  checking a provider exists from its login page).
- `reference/roles-and-models.md`: administrator / contributor / auditor from Keycloak; admins set model Defaults
  and mapping; new datasets use the Defaults; chat model choices for everyone.
- `reference/sessions-and-sign-in.md`: idle timeout, My sessions, cookie, client IP, sign-in limits, TOTP.
- `reference/ui-and-onboarding.md`: Access map, product tour (voice-over, phone/computer versions), mobile,
  shortcuts and onboarding.
- `reference/quick-start.md`: the guided one-workflow Quick start (phone + web), merge files, extraction workflow.
- `reference/chat-design.md`: the Claude-style chat layout for Lapi Agent and the Dashboard chat.
- `reference/spreadsheets-and-charts.md`: XLSX/CSV/TSV with row-aware indexing, exact `query_table` answers, charts.
- `reference/mobile-agent-first.md`: the agent-first phone version, screen control through OpenFGA, agent training, and phone design D (answer-first Home, raised Add tab, bottom-sheet sources, mapping badges, previewing with a stand-in API).
- `reference/deploy-pitfalls.md`: all three images (api, web, keycloak) must carry the release tag; failed-create recovery.
- `reference/ocr-dense-pages.md`: read a dense scanned page in strips when the OCR answer is cut off.
- `reference/agent-guide.md`: deterministic guide layer for plain requests (upload this / pull out / create dataset) before the model.
- `reference/skills-that-apply.md`: SKILL.md upload/download and applies_to matching so the agent uses skills by itself.
- `reference/workbooks-connected.md`: read every part of an .xlsx (formulas, comments, images via OCR, charts, text boxes, embedded files), connect them to rows and sheets, meaning profiles, extraction by meaning with confirmation, chat joins and row context; coverage report so nothing is dropped silently.
- `reference/tour-video.md`: narrated motion video for the tour from Python + edge-tts + ffmpeg, and its player.

## How the user works (follow this)

- Explain in plain language, with short sections; the user is not always a security specialist.
- **Show a plan first** for anything large; ask the decisions that are genuinely theirs (below), then build.
- The user often sends follow-up requests **while you are working** ("also do X", "one for mobile and one for web").
  Fold them into the current release when they belong to it; say how you are handling them.
- **Never deploy to production, and never change a production database, without the user's explicit go-ahead
  in chat** for that deploy ("Goahead", "Publish it", "deploy it" count for the release just discussed). Show the
  Terraform plan summary and the environment-variable changes first.
- **Never type, print or store real passwords, API keys or tokens.** Generate secrets in Terraform into OCI Vault;
  the person reads them in the OCI Console. Local demo test values are fine only in local demo files.
- Work on a branch, run the tests, then push and open a PR with a clear description; merge only when asked.
- Release discipline (Lapi): bump `application-version.json` (also the in-app "What's new"), `CHANGELOG.md` and
  the README version line per release; one version per deploy.
- Test end to end yourself before saying done: backend suite, frontend type-check + tests, and the screen in a
  browser at phone (375), tablet (820) and desktop (1280) sizes in the local demo.
- Long independent pieces can run in a background helper in its own `git worktree`; merge after.
- When the user shares a screenshot of a problem, reproduce it (same screen size, same role) before fixing.

## Decisions to ask the user before starting

1. **Keycloak**: host it (same server, Oracle schema, no extra cost) or connect the company's Keycloak? Or later?
2. **Access levels**: Viewer / Editor / Owner per dataset + Auditor (recommended), or keep one level?
3. **Tour format**: animated in-app (recommended: no video files, easy to update) or an MP4 recording?
4. **Hostname**: sslip.io name (`app.<ip>.sslip.io`, free) or the company's domain (needs a DNS A record).
5. Anything that affects people: once Keycloak is on, everyone except break-glass admins signs in through it,
   so existing password users need Keycloak accounts (the user creates or invites them, not Claude).
6. Company sign-in: which providers (Lapi: "Both" Microsoft and Google, "straight to provider" buttons); the person
   registers the apps in Google Cloud / Entra themselves.

## Order of work (each phase = its own branch, tests, PR, and deploy only on go-ahead)

### Phase 0 - HTTPS (do this first; plain HTTP to a bare IP is blocked by many company networks)
Symptom that triggered it in Lapi: a colleague got `ERR_CONNECTION_TIMED_OUT` on `http://<ip>` while the
HTTPS Aegis site worked. Follow `reference/https-caddy-sslip.md`. Key points:
- Caddy in the app's container instance, LB listeners 80/443 as **TCP pass-through**; port 80 redirects.
- Let's Encrypt issues **5 certificates per week** for the same name, and every deploy replaced the server, so
  **save Caddy's data folder to object storage and restore it before Caddy starts** (`tls_state.py`).
- Run **Caddy as the api's uid** - Caddy keeps files owner-only; as root the api could not read them and the
  folder scan silently found nothing (bug we hit, fixed in v26.1.16.16).
- First save must compare against **what was restored**, not the folder at loop start (bug fixed in v26.1.16.15).
- Terraform: removing an LB backend set still used by a listener gives **409**; move the listener first
  (`terraform apply -target=<listener>`), then apply the rest.
- Set `COOKIE_SECURE=true` and the public URL to `https://...`.

### Phase 1 - Authorization (OpenFGA) and access controls
Read `reference/route-policy.md` and `reference/openfga-model.json`.
1. Add `access_level` to the person→dataset grant table (nullable; **migrate existing grants to `editor`**
   so nobody loses abilities); add tables `team_tbl`, `team_member_tbl`, `team_dataset_tbl`, `workspace_role_tbl`.
   **Do not alter Oracle CHECK constraints** on the users' role column: put Auditor in its own table.
2. OpenFGA model: `dataset` owner ⊃ editor ⊃ viewer, grants to `user` and `team#member`, `lapi:workspace`
   administrator, auditor and contributor. In-memory store, **rebuilt from the database** on start or when the
   store is missing; sync after each commit (SQLAlchemy `after_flush`/`after_commit`); **fail closed** (503) when
   unreachable.
3. Enforce levels in routes (`get_record(..., level='editor')`, `require_level(actor, dataset_id, 'owner')`).
4. **Route policy table**: every `(method, path)` → public / signed_in / viewer / editor / owner / contributor /
   audit / admin. `auth()` looks up `request.scope['route'].path`, enforces admin/contributor/audit centrally,
   and **refuses unclassified routes**. A test walks all routes - including FastAPI 0.14x **`_IncludedRouter`**
   (`route.original_router.routes`) - and fails on missing or stale entries. Also update any API-documentation
   catalog that lists operations.
5. Keycloak groups → teams at each sign-in; Auditor and Contributor from Keycloak roles.
6. UI: Access map (graph + grid + teams, read-only for Auditors), Manage dataset "Members" tab for Owners,
   "Your access" label and Viewer-hidden actions, Auditor role option in Users & passwords.
7. Tests: fake OpenFGA must understand computed relations and `team#member` (see route-policy reference).
   Old tests that assumed "any grant can upload" must grant Editor explicitly.

### Phase 2 - Authentication hardening (Keycloak + sessions) — live in Lapi
Read `reference/keycloak-realm.md`, `reference/sessions-and-sign-in.md` and `reference/company-sign-in.md`.
- Hosted Keycloak (custom image with the Oracle JDBC driver, `KEYCLOAK` DB user created idempotently by the api
  from a Vault password, secrets handed to Keycloak via a scratch-volume folder + ready marker, realm import with
  `${ENV}` placeholders so the client secret is not in Terraform state, `sso.<ip>.sslip.io` through Caddy).
- Realm: brute-force lockout, password policy, SSO idle 30 min / max 12 h, group-membership mapper (`groups`,
  full path), AMR mapper, OTP for the administrator role (conditional flow), back-channel logout URL; roles
  `<app>-administrator`, `<app>-auditor`, `<app>-contributor`.
- App: PKCE S256 + state + nonce + issuer + `azp` checks; store Keycloak `sid` and encrypted refresh/ID tokens on
  the session; **re-check with a refresh-token grant every 5 minutes** (ends disabled/signed-out people, refreshes
  roles and teams); **back-channel logout** endpoint; `id_token_hint` on sign-out. `REQUIRE_ADMIN_MFA` exists but
  the user chose **"rely only on Keycloak"** (`false`; enforce OTP in Keycloak) after it blocked admins whose
  `amr` lacked `otp`.
- Company sign-in buttons (`kc_idp_hint`) driven by Terraform `keycloak_identity_providers`; the custom browser flow
  must keep the Identity Provider Redirector step or the button lands on Keycloak's page; the popup never says
  "Keycloak" (work account / Google / username and password / emergency administrator sign-in).
- Sessions: 30-minute idle timeout, "My sessions", admin "sign out everywhere", `__Host-` cookie with HTTPS.
- Sign-in limits in the database (5 per username / 20 per address per 15 min), TOTP for break-glass accounts.
- Client IP: trust `X-Forwarded-For` only from loopback; **PROXY protocol v2** on the LB TCP listeners + Caddy.

### Roles and models (v26.1.16.21-.22) — read `reference/roles-and-models.md`
- Keycloak role `<app>-contributor` = everything except Manage workspace; give it to everyone via the realm's
  **Default roles** for a "play around" period, remove it there to end it.
- Only administrators set model Defaults and map models; new datasets use the Defaults; everyone can pick a chat
  model from `chat_choices`.

### Phase 3 - Audit and protection (next; not built yet in Lapi)
- Append-only `audit_event` table: sign-ins (and failures), role/access/team changes, deletions, exports,
  setting changes, break-glass use; Audit log screen for Administrators and Auditors with filters + CSV export.
- Security headers in Caddy: HSTS, CSP with `frame-ancestors 'none'`, Referrer-Policy, Permissions-Policy,
  X-Content-Type-Options.
- OpenFGA preshared key (`OPENFGA_AUTHN_METHOD=preshared`); make settings/capabilities endpoints admin-only;
  set `ALLOWED_ORIGINS` to the public URL. Later: least-privilege DB user, remote encrypted Terraform state,
  malware scanning of uploads.

### Product experience (can run in parallel with any phase)
- Tour: `reference/ui-and-onboarding.md` (60 s animated, shown once, narrated with speech synthesis, separate
  phone and computer versions).
- Quick start: `reference/quick-start.md` (one guided workflow, consent before AI, AI-drafted extraction fields,
  merge files, extraction workflow, results + Review in the same popup, tablet scrolling, Enlarge).
- Chat: `reference/chat-design.md` (centred column, serif answers, question bubbles, rounded composer, live status;
  the answer-workflow panel never opens by itself — a slim status line instead).
- Spreadsheets and charts: `reference/spreadsheets-and-charts.md`.
- Agent-first phones and screen control: `reference/mobile-agent-first.md` (Release 2 planned: Azure and other
  stores through the agent with secure fields, consent and once-or-keep; review-in-chat; share-by-chat; /Datasets).
- Mobile compact layouts, keyboard shortcuts (`?` lists them) and "ask first, then guide" set-up questions.
- **Workspaces above collections** (Lapi 26.1.16.44+; `lapi_app/workspaces.py`, `app/workspace-gate.tsx`, `app/workspace-scope.ts`): Workspace → Document Collection (the old "dataset") with a free type tag. Ask which workspace at login; with none, walk through creating one, then a collection. Workspaces are `core.Record` rows, no new table, and access stays on collection grants: members are copied onto each collection's grants, so OpenFGA did not change. Everyone gets 1 personal + 1 team workspace, and only administrators are unlimited; the limit counts only workspaces you created. Existing data moves lazily: unshared to the owner's personal workspace, shared to one "Organization" workspace, keeping today's access. Whoever triggers that move must not become its owner. Scope every list by the open workspace, including jobs, extractions and templates, or an empty workspace shows another workspace's "Check 1 file".
- **Phone chat layout** (Lapi 26.1.16.45; `phone-design.css`, `agent-v2.tsx`, `page.tsx`): one row at the top (workspace name as the title, an amber dot with a count for files that need the person, an account circle whose menu holds Sign out); a personal greeting ("Hi Mani, how can I help?" from the sign-in name) with the collection as a chip; three big starter cards (Add documents, Pull out data, Summarize my files); one clean input bar with the collection chip opening an options sheet (collection, model, history, new, clear, about); Quick Extract results as figure cards; a floating rounded tab bar. Keep the computer layout unchanged: branch on `device==='phone'` from `useDevice()` and the same media query.
- **Access by grant, never by role** (26.1.16.45): administrators and contributors open only what they created or were given, like everyone else; the creator keeps a collection until someone removes them (a disabled `UserDataset` row records that). Personal workspaces are never listed to anyone else; administrators look after the Organization workspace only.

## Production deploy routine (Lapi on an OCI Container Instance)
1. Commit; `docker build --platform linux/amd64` api (`INSTALL_ORACLE=true INSTALL_OCI=true
   INSTALL_CLOUD_MODELS=true INSTALL_LOCAL_EMBEDDINGS=false`) and web; retag keycloak when unchanged; push all
   three to `ap-mumbai-1.ocir.io/<namespace>/lapi/{api,web,keycloak}:<version>` (api only needs rebuilding when
   backend code changed, but every image needs the new tag).
2. `terraform plan -var image_tag=<version> -out=<file>`; expect "3 to add, 3 to destroy" (instance + two LB
   backends); report any `LAPI_*` env changes; apply **the saved plan** only after the go-ahead.
3. Update helper scripts that hold the container-instance OCID (status, logs, DB job).
4. Verify: all containers ACTIVE, `/api/auth/status` 200, sso discovery 200, HTTP → 308, the new version string
   and a new UI string present in the served JS/CSS bundles, api log "Application startup complete" without
   tracebacks, both LB backend sets OK (can read CRITICAL for a minute right after).
5. Push the branch (the open PR picks it up); tell the user what to try on the live site and what was not verified.

## Where Aegis differs (check before applying)

- Prefix `ags_` (`ags_backend/ags_app`, `ags_frontend`, `ags_deploy`, `ags_testing`); version line `v26.1.13.x`.
- Deployed on **OKE (Kubernetes)** via `ags_deploy/Deploy-Aegis.ps1` and release tooling, already on HTTPS at
  `https://aegis.92.4.67.183.sslip.io` with a **Caddy pod and a persistent volume** - so the certificate
  persistence work (Phase 0) is mostly unnecessary there; translate Terraform container-instance steps into
  Kubernetes manifests/Helm values (Deployments, Services, Secrets from OCI Vault, NetworkPolicies).
- No Keycloak or OpenFGA yet: `ags_app/dataset_access.py`, `user_management.py` and `main.py` match Lapi's
  pre-phase-1 shape, so Phase 1 maps almost one to one; run OpenFGA as a sidecar or a small Deployment.
- Aegis has strict release receipts and protected-resource fingerprints in `ags_deploy`; follow its README's
  release procedure rather than Lapi's Terraform flow, and still get the user's go-ahead before any release.
- Check whether Aegis's chat components share classes like Lapi's `agent-v2-*` before porting `chat-design.css`.

## Lapi files to copy patterns from (all under `C:\Users\Laya\Documents\Lapi`)

| Piece | Files |
|---|---|
| HTTPS + certificate persistence | `lapi_deploy/lapi_containers/{containers,loadbalancer,network}.tf`, `lapi_backend/lapi_app/tls_state.py`, `lapi_testing/backend/test_tls_state.py` |
| OpenFGA sync and checks | `lapi_backend/lapi_app/authz.py`, `lapi_testing/backend/test_openfga_authz.py` (FakeOpenFGA) |
| Levels, teams, Auditor, Contributor | `lapi_backend/lapi_app/{dataset_access,teams,relational,user_management}.py` |
| Route policy | `lapi_backend/lapi_app/route_policy.py`, `main.py` (`auth`), `lapi_testing/backend/test_route_policy.py` |
| Keycloak OIDC + roles + providers | `lapi_backend/lapi_app/keycloak_auth.py`, `keycloak_bootstrap.py`, `lapi_deploy/keycloak/`, `lapi_testing/backend/test_keycloak_auth.py`, `lapi_docs/company-sign-in.md` |
| Model Defaults for new datasets | `lapi_backend/lapi_app/dataset_models.py` (`migrate`, `routing_public` `chat_choices`), `workspace_defaults.py` |
| Sessions, limits, TOTP | `lapi_backend/lapi_app/{sessions,sign_in_limits,totp}.py`, `lapi_testing/backend/test_sign_in_hardening.py` |
| Access map UI | `lapi_frontend/app/access-map{.tsx,-data.ts,.css}`, `dataset-members.tsx`, `manage-dataset.tsx` |
| Account security UI | `lapi_frontend/app/account-security.tsx`, `user-management.tsx`, sign-in form in `page.tsx` |
| Product tour | `lapi_frontend/app/walkthrough{.tsx,-data.ts,.css}`, `lapi_backend/lapi_app/walkthrough.py` |
| Quick start | `lapi_frontend/app/quick-start{.tsx,-flow.ts,.css}`, `workspace-assist.tsx`, `lapi_backend/lapi_app/prompt_suggest.py` |
| Chat design | `lapi_frontend/app/{chat-design.css,chat-phase.ts,agent-v2-chat.tsx,agent-answer-workflow.tsx}`, `agent-workspace.css` |
| Spreadsheets and charts | `lapi_backend/lapi_app/spreadsheet.py`, `worker.py` (`chunk_pages`, `table_chunks`), `lapi_agent/agent_tools_v2.py` (`query_table`), `lapi_frontend/app/answer-chart{.tsx,-data.ts}`, `lapi_testing/backend/test_spreadsheets.py` |
| Local Keycloak demo | `lapi_local_use/keycloak-demo/` (compose, realm, start script, README) |
| Screen control, training | `lapi_backend/lapi_app/screens.py`, `lapi_frontend/app/{screens-client.ts,screens-admin.tsx,agent-training.tsx}`, `lapi_testing/backend/test_screens.py` |
| Release notes | `CHANGELOG.md` entries v26.1.16.13 to v26.1.16.27 |

## Pitfalls we actually hit (avoid them)

- Bash heredocs mangle backslashes and `\n` (`\'`, `\d`, `\n`, unmatched quotes): write files with the Write/Edit
  tools, or put Python edit scripts in a file. PowerShell `+=` on a one-line `Get-Content` result concatenates
  strings (it corrupted a `.env`).
- Long Windows paths break `docker -v` mounts: use short folders like `C:\Users\<you>\AppData\Local\Temp\lt5`.
- Frontend tests in Docker: copy the app into the container (`cp -r /src/... /w/...`), run `npm ci` there and set
  `NODE_PATH=/w/lapi_frontend/node_modules`; `npm ci` on the Windows-mounted folder silently fails. Copy
  `CHANGELOG.md` and `README.md` too (the About test reads them).
- PowerShell splits `-target=a.b` - quote Terraform arguments: `'-target=oci_load_balancer_listener.http'`.
- Port 3000 may be taken locally; the Keycloak demo uses 3100. Keycloak's issuer must be identical for the
  browser and the api (demo: api/web share Keycloak's network namespace so both use `localhost:8180`).
- `docker compose up -d web` may not recreate the container after an `.env` image change: use `--force-recreate`;
  the browser may also show a cached page — add a query string to the URL.
- Only Keycloak re-imports a realm into an empty data store: `docker compose down -v` to re-import; in production
  add new roles by hand in the admin console (the realm file only helps new installs).
- Frontend unit tests: 19 fail on `main` already - compare failing names against `main` (`lt5/fail-main.txt`),
  not the count.
- After every deploy the container instance OCID changes: update helper scripts (status/logs) that hold it.
- LB backend health can read CRITICAL for a minute right after a deploy; re-check before alarming the user.
- Keycloak admin console: users and roles must be created in the **app realm**, not `master`; the Assign-role
  dialog opens on client roles — switch to realm roles.
- Grid dialogs with `max-height`: give the row `minmax(0,1fr)` or the body never scrolls (tablet bug).
- Browser speech synthesis needs a user gesture; handle `not-allowed` with a visible "Turn on voice" button.
- A function recreated every render inside an interval's dependency list restarts the timer every render: wrap
  it in `useCallback`.
- "I see no changes" after a deploy: the page HTML was cached by the browser (Next sends only `s-maxage`). Caddy
  now sends `Cache-Control: no-cache` for pages (`header @pages >Cache-Control "no-cache"`, not `/_next/static`).
- When the product tour version changes, the tour opens on the next Dashboard visit — close it before scripting
  clicks in a browser test.
- Mock models in the local demo cannot plan, answer or suggest fields: test UI states with a scripted fetch
  stream or manual inputs, and say what was not verified with real models.
