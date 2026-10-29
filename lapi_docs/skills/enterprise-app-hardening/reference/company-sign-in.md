# Company sign-in (Microsoft, Google, GitHub…) through Keycloak, and Keycloak troubleshooting

## Design (Lapi v26.1.16.20)
- Providers are **Keycloak identity providers** in the app's realm; the app never talks to Google/Microsoft.
- Terraform `keycloak_identity_providers` (map alias → label) becomes an env var; `GET /api/auth/status` returns
  `providers`, and the sign-in page shows one button per provider ("Sign in with Microsoft/Google/GitHub", logos)
  that goes **straight to the provider** with `kc_idp_hint=<alias>`, plus "Use a Keycloak account instead".
  Buttons stay hidden until the variable lists providers (so nothing broken shows before set-up).
- Guide for the person: `lapi_docs/company-sign-in.md` (Google: Google Cloud console → OAuth consent screen →
  Credentials → OAuth client ID (Web) → redirect URI `https://sso.<host>/realms/<realm>/broker/google/endpoint` →
  paste client ID/secret in Keycloak → Identity providers → Google). Explain *why* the cloud console is needed:
  Google only lets a registered app ask people to sign in, and the secret is what proves it is your Keycloak.
- Works on phones the same way (redirects only).

## Troubleshooting we did in production (repeat these checks)
- **"I created a user but cannot sign in"**: the user was created in the **master** realm. Users for the app live
  in the app realm (`lapi`); switch the realm picker (top left) before creating users or roles. Admin console link:
  `https://sso.<host>/admin/master/console/#/lapi`.
- **"lapi-administrator role not listed"**: it is a realm role in the app realm (Realm roles), and when assigning,
  switch the dialog's filter from clients to **realm roles**.
- **Sign-in loops back to the sign-in page / "Sign in with Keycloak" just refreshes**: the app refused the identity.
  In Lapi it was the admin MFA check (`amr` had no `otp`) — the user chose "rely only on Keycloak", so
  `LAPI_KEYCLOAK_REQUIRE_ADMIN_MFA=false` (enforce OTP in Keycloak's flow instead). Check the api log for
  `SignInFailed` reasons and show the code on the sign-in page.
- New Keycloak users appear in the app only after their **first sign-in** (just-in-time provisioning); sharing a
  dataset with someone needs them to sign in once first.
- Role changes apply at the next sign-in or within 5 minutes (re-check); a role change on administrator signs the
  person out everywhere.
- `ORA-28007: the password cannot be reused` in the api log at start-up is harmless (the bootstrap tries to reset
  the Keycloak DB password to the same value).
- Never paste real passwords into chat or screenshots; if one was shown, tell the person to change it.

## Wording (v26.1.16.28)
People do not know what Keycloak is, so the sign-in popup never names it: the description is "Choose how you
want to sign in" (with provider buttons) or "Sign in with your work account"; the fallback link is "Sign in with a
username and password instead"; the local-admin form is "Emergency administrator sign-in"; error texts say
"sign-in service". Keep the provider list in Terraform, and check the provider exists in Keycloak first by
fetching its login page with PKCE parameters and looking for `broker/<alias>`.
