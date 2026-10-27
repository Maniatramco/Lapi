# Gmail connector plan

Status: planned, not built. Start once Lapi has a domain name served over HTTPS.

## Why it waits for a domain with HTTPS

A personal gmail.com mailbox can only be read after its owner signs in with Google and consents
("Connect with Google"). Google sends the user back to a redirect URI that must be HTTPS on a
domain name; it refuses plain `http://` and raw IP addresses such as `http://92.4.94.96`.
Google Workspace mailboxes can also be read by a service account with domain-wide delegation,
but that also needs a Workspace administrator, so the OAuth flow is the one to build first.

## Prerequisites (infrastructure)

1. A domain name (for example `lapi.example.com`) with a DNS `A` record to the load balancer IP.
2. An HTTPS listener on the OCI load balancer with a certificate for that name (OCI Certificates
   or Let's Encrypt), and HTTP redirected to HTTPS.
3. Terraform: `public_url = "https://lapi.example.com"` and `COOKIE_SECURE = "true"`.
   This also lets the Keycloak redirect URI move to HTTPS.
4. A Google Cloud project with the Gmail API enabled and an OAuth client of type
   "Web application", redirect URI `https://lapi.example.com/api/source-connections/gmail/callback`.
   The client secret goes into OCI Vault like the Keycloak client secret; Lapi never stores it in
   configuration files.

## Google review

- Scope: `https://www.googleapis.com/auth/gmail.readonly` only. Google classes it as a
  restricted scope.
- While the OAuth consent screen is in Testing, only test users added by hand (up to 100) can
  connect, and their consent expires after 7 days.
- Opening it to any Google account needs Google's app verification and an annual third-party
  security assessment (CASA) for restricted scopes. Plan for weeks, not days.

## Design

- New provider `gmail` in `source_connections.py` / `cloud_sources.py`, reusing the existing
  browse, import, index and publish path, so imported mail is vectorized exactly like files.
- Connecting: OAuth authorization code flow with PKCE, the same pattern as
  `keycloak_auth.py` (encrypted short-lived flow cookie, state and nonce checks). Request offline
  access; store only the refresh token, encrypted with the master key like other connection
  credentials. Each connection belongs to the user who connected it.
- Browsing: labels act as folders; messages are listed newest first, 100 per page, with an
  optional Gmail search filter saved on the connection (for example `from:billing@ newer_than:1y`).
- Importing: each message becomes one TXT document (From, To, Date, Subject, plain-text body;
  HTML bodies converted to text). PDF, DOCX, TXT and JSON attachments import as separate documents
  linked to the message. The revision is the message ID plus its history ID.
- Read-only: Lapi never sends, deletes, labels or marks mail as read. Removing the connection
  revokes the refresh token with Google.
- Not in the first version: automatic sync of new mail (the same manual-import rule as the other
  connectors applies), shared/delegated mailboxes, Google Workspace domain-wide delegation.

## Tests

- Fake Google OAuth and Gmail API (like `FakeKeycloak` in `test_keycloak_auth.py`): consent
  flow, state/PKCE checks, refresh-token encryption, refusal of other users' connections.
- Message to text conversion, attachments, pagination, label scoping, revocation on delete.
- Manual end-to-end check with a test Gmail account added as an OAuth test user.

## Rough size

About the same as the Keycloak work: backend flow and adapter, form changes, tests, a Terraform
variable for the OAuth client and its Vault secret. The HTTPS listener and domain come first.
