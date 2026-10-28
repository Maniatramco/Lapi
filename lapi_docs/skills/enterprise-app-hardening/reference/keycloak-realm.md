# Keycloak: realm, client and the app's OIDC handling

## Realm (`lapi` in Lapi; see `lapi_local_use/keycloak-demo/realm-lapi.json` for a working local example)
- Roles: `<app>-administrator`, `<app>-auditor`, `<app>-contributor` (Lapi: `lapi-administrator`, `lapi-auditor`,
  `lapi-contributor`; what each grants: `roles-and-models.md`). Adding the contributor role to the realm's
  **Default roles** gives it to everyone.
- Security: `bruteForceProtected: true`, `failureFactor: 5`; password policy
  `length(12) and notUsername and notEmail and passwordHistory(5)`; SSO session idle 30 min, max 12 h;
  access token 5 min.
- Client `<app>` (confidential, standard flow only, PKCE `S256`):
  - redirect URI `https://<app host>/api/auth/keycloak/callback`; post-logout `https://<app host>/`;
  - back-channel logout URL `https://<app host>/api/auth/keycloak/backchannel-logout`, session required;
  - protocol mappers: **Group Membership** (`claim.name: groups`, `full.path: true`, ID + access token) and
    **AMR** (`oidc-amr-mapper`, claim `amr`, ID + access token).
- **OTP for administrators**: copy the browser flow; after username/password add a conditional subflow with
  "Condition - user role" = administrator role that requires OTP (configure TOTP on first use); bind it as the
  realm browser flow.
- Client secret in a realm import: use `${LAPI_CLIENT_SECRET}`-style env placeholders so the value is not in
  Terraform state; a wrapper command exports it from a secrets file before `kc.sh start --optimized --import-realm`.
- A realm import only applies to an empty Keycloak; re-import locally with `docker compose down -v`.

## Hosting Keycloak next to the app (Lapi phase 2 design)
- Same container instance (no extra cost; ~1-1.5 GB memory), `KC_HTTP_HOST=127.0.0.1`, port 8180, behind Caddy
  at `https://sso.<ip>.sslip.io` with `KC_PROXY_HEADERS=xforwarded`, `KC_HOSTNAME=https://sso...`.
- Database: a `KEYCLOAK` user in the existing Oracle Autonomous DB (TLS, no wallet). The official image does not
  ship the Oracle driver: build a custom image adding `ojdbc11` + `orai18n` (pinned, checksummed) to
  `/opt/keycloak/providers/`, `KC_DB=oracle`, `kc.sh build`. The api creates the user idempotently from a Vault
  password (least privileges: CREATE SESSION/TABLE/SEQUENCE/VIEW/PROCEDURE/TRIGGER, quota) and writes
  `db-password`, `admin-password`, `client-secret` (0600) + `.ready` into a scratch folder Keycloak waits for.
  **Creating the DB user is a production DB change: get the user's explicit OK at deploy time.**
- Keycloak 26 keeps user sessions in the DB (persistent sessions), so sign-ins survive deploys.
- The bootstrap admin password lives in Vault; the person reads it in the OCI Console - never print it.
- After Keycloak is on, password sign-in is only for local administrators (break-glass); everyone else needs a
  Keycloak account (the user creates/invites people).

## App-side OIDC (`keycloak_auth.py`)
- Start: state, nonce, PKCE verifier in an encrypted, path-scoped, 10-minute flow cookie (SameSite=Lax);
  `_safe_next` only allows same-site paths.
- Callback: exchange code with `code_verifier` + client secret; verify ID token signature (JWKS, re-fetch on
  unknown kid), issuer from discovery (must equal configured issuer), audience, nonce, and **`azp`** when there
  are several audiences or `azp` is present. Roles from realm/client roles in the ID and access tokens.
- Provision: account id `kc-<sub>`, never merge with a local account of the same username (409 conflict);
  role, Auditor (`workspace_role_tbl`) and team memberships follow Keycloak at every sign-in; a role change
  signs the person out everywhere.
- Session: store Keycloak `sid` and **encrypted** refresh + ID tokens on the session row.
- **Re-check every 5 minutes** in `authenticate()`: refresh-token grant; 400/401 → end the session ("Your
  Keycloak session has ended"); success → re-verify tokens, re-provision (roles/teams), save new tokens;
  Keycloak unreachable → keep the session and retry later (log it).
- **Back-channel logout** `POST /api/auth/keycloak/backchannel-logout` (public route, form field
  `logout_token`): verify signature, issuer, audience, `iat`; require the back-channel logout event, refuse a
  `nonce`; end sessions by `sid` (or by `sub` when no sid). Return 200 / 400.
- Sign-out: Keycloak end-session URL with `client_id`, `post_logout_redirect_uri` and **`id_token_hint`**
  (otherwise Keycloak shows "Do you want to log out?").
- Optional `LAPI_KEYCLOAK_REQUIRE_ADMIN_MFA=true`: refuse an administrator whose `amr` has no
  `otp`/`mfa`/`hwk`/`swk`/`webauthn` (sign-in error code `mfa_required`, shown on the sign-in page).

## Local demo (for showing the user and for manual tests)
`lapi_local_use/keycloak-demo/` runs Keycloak 26.0.7 + OpenFGA + api + web with `network_mode: service:keycloak`
so the browser and the api both reach Keycloak as `localhost:8180` (issuer matches). Lapi is on
`http://localhost:3100`. **Local demo test accounts only**: alice (administrator), bob (user, group Finance),
carol (auditor); passwords are in that README and must never be reused anywhere real.
Checks: alice lands as Administrator; bob's group becomes team Finance; give Finance Editor in the Access map and
bob can upload; carol sees Users & passwords and Access map read-only and no datasets; the tour opens on first
sign-in; sign-out ends the Keycloak session.
