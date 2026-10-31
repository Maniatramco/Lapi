# Sessions, sign-in limits and TOTP (Lapi phase 2, `sessions.py`, `sign_in_limits.py`, `totp.py`)

## Sessions
- Session row (`Login`): id = SHA-256 of the cookie token, owner, absolute `expires` (12 h), `csrf`, plus new
  nullable columns `last_seen`, `user_agent`, `client_ip`, `kc_sid`, `kc_tokens` (encrypted), `kc_checked`.
  The startup upgrade adds missing columns with `ALTER TABLE ... ADD` (nullable) - keep model columns Optional.
- `authenticate()`: look up by hash → `sessions.check(login)` raises 401 for expiry or **idle > 30 minutes**
  (`LAPI_SESSION_IDLE_MINUTES`); CSRF on non-GET; record activity at most once a minute; Keycloak re-check
  every 5 minutes.
- Cookie: `__Host-<app>_session` when HTTPS (Secure, Path=/, no Domain), else the plain name; HttpOnly,
  SameSite=Strict. Read both names during the transition; clear both on sign-out. Centralize set/clear/read
  in one module and replace every direct `set_cookie`/`delete_cookie` (we found them in main, Keycloak callback,
  user management and browser recovery).
- Endpoints: `GET /api/me/sessions` (16-char id prefix, current flag, created, last active, address, browser,
  sign-in method), `DELETE /api/me/sessions/{short_id}`, `POST /api/me/sessions/sign-out-others`,
  admin `POST /api/users/{id}/sessions/sign-out`. Never return the CSRF token or the full hash.
- Encrypt stored Keycloak tokens with the master key (Fernet); fall back to a per-process key in tests.

## Client address
Requests go Caddy → Next.js proxy → api on one host, so the api sees `127.0.0.1`. Trust the **last**
`X-Forwarded-For` entry only when the peer is loopback (Caddy replaces the header with the address it saw).
For Caddy to see real addresses behind an OCI TCP load balancer, enable **PROXY protocol v2** on the LB
listeners (`connection_configuration { backend_tcp_proxy_protocol_version = 2 }`) and Caddy's
`listener_wrappers { proxy_protocol { allow <LB subnet> } tls }`; make sure TCP health checks still pass.

## Sign-in limits (database, survive restarts)
- Table `sign_in_attempt_tbl(attempt_key PK, failures, window_start, locked_until)`; keys are
  `user:` / `ip:` + SHA-256 of the value (no usernames or IPs in clear).
- 5 failures per username in 15 min → that username locked 15 min; 20 per address → address locked.
  A success clears only the username key, so an attacker cannot unlock themselves with another account.
- Replaces the old in-memory per-`request.client.host` counter, which counted everyone together (all requests
  arrive from the proxy) and was reset by any success.
- Unknown usernames still run a password hash (`_UNKNOWN_USER_HASH`) so timing does not reveal accounts.
- Record failures **after** leaving the sign-in transaction (SQLite locks otherwise).
- Keycloak accounts rely on Keycloak's brute-force detection.

## TOTP for break-glass password accounts (RFC 6238, no extra library)
- Table `user_totp_tbl(user_id, secret (encrypted), enabled, last_step)`.
- `POST /api/auth/totp/setup` (current password) → base32 key + `otpauth://totp/<App>:<user>?secret=...&issuer=<App>`;
  `POST /api/auth/totp/confirm {code}`; `POST /api/auth/totp/disable {current_password, code}`;
  admin `POST /api/users/{id}/totp/reset {current_password}` (signs them out). Keycloak accounts get 409
  ("set up MFA in Keycloak").
- Verify ±1 step of drift and **refuse steps ≤ last_step** (no replay).
- Sign-in: correct password + enrolled account without a code → 401 "Enter the 6-digit code from your
  authenticator app." (not counted as a failure); the sign-in form shows a code field
  (`inputMode=numeric`, `autoComplete=one-time-code`) when the message mentions the authenticator.
- Log a WARNING for every break-glass password sign-in while Keycloak is on (phase 3 turns it into an audit event).

## Tests (Lapi `test_sign_in_hardening.py`)
Idle timeout and activity, My sessions/sign-out/others/admin sign-out, `__Host-` cookie flags, username and
address lockouts with hashed keys, success clears only the username, trusted client address, TOTP setup/confirm,
code required, replay refused, admin reset permissions, Keycloak re-check (role removed → signed out; revoked →
"session has ended"), back-channel logout (bad token 400, nonce 400, valid ends the session), admin MFA required.
Extend the fake Keycloak with a refresh-token grant, `sid` and `amr`.

## Sign-in and sign-out start fresh (Lapi, after v26.1.16.41)
A single-page app keeps its old code and state across a password sign-in or sign-out unless the page reloads, so people
saw "changes not applied" after a deploy. `startFresh` (chat-login-session.ts) does a full page load to the site root after
both; sign-out also clears sessionStorage. A tab left open without signing out still runs old code until it reloads.

