# Sign in with Microsoft or Google (through Keycloak)

People sign in to Lapi with their work Microsoft or Google account. Keycloak (hosted at
`https://sso.92.4.94.96.sslip.io`) talks to Microsoft and Google; Lapi shows one button per
provider and goes straight to it. Accounts are created in Keycloak at the first sign-in; you
still give roles (`lapi-administrator`, `lapi-auditor`) and groups in Keycloak, and dataset
access in Lapi's Access map.

You do steps 1–4 (they involve your company's admin consoles and secrets). Then Lapi is told
which providers exist (step 5) and the buttons appear.

Keycloak's address for each provider (you will paste these):

| Provider | Redirect URI |
|---|---|
| Microsoft | `https://sso.92.4.94.96.sslip.io/realms/lapi/broker/microsoft/endpoint` |
| Google | `https://sso.92.4.94.96.sslip.io/realms/lapi/broker/google/endpoint` |

## 1. Microsoft: register Lapi in Microsoft Entra ID

1. Open **https://entra.microsoft.com** (or Azure portal → **Microsoft Entra ID**) as an administrator.
2. **App registrations → New registration**:
   - Name: `Lapi`
   - Supported account types: **Accounts in this organizational directory only** (only your company).
   - Redirect URI: platform **Web**, value: the Microsoft redirect URI above.
   - **Register**.
3. On the app's **Overview**, copy **Application (client) ID** and **Directory (tenant) ID**.
4. **Certificates & secrets → Client secrets → New client secret** (description `Keycloak`, 24 months)
   → copy the **Value** now (it is shown only once). Put a reminder to renew it before it expires.
5. **API permissions**: `User.Read` (default) is enough. If your tenant asks, click
   **Grant admin consent**.

## 2. Microsoft: add it to Keycloak

1. **https://sso.92.4.94.96.sslip.io/admin**, sign in as `kcadmin`, switch the realm to **lapi**.
2. **Identity providers → OpenID Connect v1.0**:
   - **Alias: `microsoft`** (exactly; Lapi's button uses it). Display name: `Microsoft`.
   - Discovery endpoint: `https://login.microsoftonline.com/<Directory (tenant) ID>/v2.0/.well-known/openid-configuration`
     (using your tenant ID keeps other companies' accounts out).
   - Client authentication: **Client secret sent as post**. Client ID: the Application (client) ID.
     Client secret: the Value from step 1.4.
   - **Add**. Then on the provider's page: **Scopes** `openid profile email`, **Trust email** on,
     **Sync mode** `Force` (name and email follow Microsoft), **Save**.

## 3. Google: create an OAuth client

1. Open **https://console.cloud.google.com** with your Google Workspace admin account and pick (or create) a project, e.g. `Lapi sign-in`.
2. **APIs & Services → OAuth consent screen**: User type **Internal** (only your Workspace users), app name `Lapi`, support email → save.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**, name `Lapi Keycloak`.
   - Authorized redirect URIs: the Google redirect URI above.
   - **Create** → copy the **Client ID** and **Client secret**.

## 4. Google: add it to Keycloak

1. In Keycloak (realm **lapi**): **Identity providers → Google**.
2. **Alias: `google`** (the default; keep it). Client ID and Client secret from step 3.
3. **Hosted domain**: your company domain (e.g. `yourcompany.com`) so only your Workspace accounts can sign in.
4. **Trust email** on, **Sync mode** `Force`, **Save**.

## 5. Tell Lapi (Claude does this)

Lapi's Terraform setting `keycloak_identity_providers = { microsoft = "Microsoft", google = "Google" }`
is added to `lapi_deploy/lapi_containers/terraform.tfvars` (not in git) and deployed (about 3 minutes;
the container instance is replaced because the setting is an environment variable). The hosted
deployment currently lists `google`. The sign-in page then shows **Sign in with Microsoft** and
**Sign in with Google**; **Use a Keycloak account instead** stays for Keycloak-only accounts, and the
break-glass administrator form stays below.

## If the button shows Keycloak's page instead of Google

Keycloak only jumps straight to the provider when its **Identity Provider Redirector** step is in the
browser flow. New installs have it (`realm-lapi.json`); an already-created realm must be fixed once by
hand: **https://sso.92.4.94.96.sslip.io/admin** → realm **lapi** → **Authentication** → flow **lapi browser**
→ **Add step** → search **Identity Provider Redirector** → **Add** → set its requirement to **Alternative**
and move it so it sits between **Cookie** and **lapi browser forms**. No restart or deploy is needed.

## Good to know

- **First sign-in**: Keycloak creates the person from their Microsoft/Google profile. If a Keycloak
  user with the same email already exists (for example one you created by hand), Keycloak asks to
  link the two accounts once.
- **Contributors**: the realm role `lapi-contributor` makes someone Owner on every dataset and lets
  them create (with the workspace Default models), delete and restore datasets, and pick a chat
  model, without mapping models or managing the workspace (users, teams, Access
  map, storage, settings, models, token usage stay with `lapi-administrator`). To give it to
  everyone, add it to the realm's default roles (Realm settings → User registration → Default
  roles → Assign role); remove it there to go back to per-dataset access. Lapi applies a change
  at the next sign-in, or within 5 minutes for people already signed in.
- **Roles**: new people are plain users. Give `lapi-administrator` or `lapi-auditor` in Keycloak
  (**Users → person → Role mapping**); it applies at their next sign-in or within 5 minutes.
- **Second factor**: people signing in with Microsoft or Google use their company's own MFA
  (Microsoft Authenticator, Google 2-Step Verification). Keep it required for administrators there.
- **Leavers**: disabling someone in Microsoft/Google stops new sign-ins; to end a running Lapi session
  at once, disable or sign out the person in Keycloak (Lapi re-checks every 5 minutes and is told
  immediately on sign-out).
- **Secrets**: the client secrets live only in Keycloak (stored in its database). Renew the Microsoft
  secret before it expires (Entra shows the date).

## Other providers (GitHub, GitLab, Okta, any OpenID Connect or SAML)

Any provider Keycloak supports works the same way: add it in Keycloak under **Identity providers**
with a short alias (`github`, `gitlab`, `okta` …), its redirect URI is
`https://sso.92.4.94.96.sslip.io/realms/lapi/broker/<alias>/endpoint`, and add the alias and button
label to `keycloak_identity_providers`. Microsoft, Google and GitHub get their own logo; others get a key icon.

**Personal accounts (GitHub, GitLab, LinkedIn, Apple …) are not controlled by your company**: anyone
with such an account could create a Keycloak account. They see nothing in Lapi until you give them
dataset access, but for an enterprise setup either keep company providers only, or in Keycloak set
that provider's **First login flow** to one that does not create accounts (link existing accounts
only), so only people you created first can use it.
