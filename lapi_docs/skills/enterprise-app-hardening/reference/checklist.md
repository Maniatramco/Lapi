# Verification and deploy-safety checklist

## Before building
- [ ] Plan shown to the user in plain language; their decisions recorded (Keycloak hosting, levels, tour, hostname).
- [ ] Branch created (or a separate `git worktree` for a parallel helper).

## Tests to write / run
- [ ] Route policy: every route classified, none stale (walk `_IncludedRouter`), unclassified refused.
- [ ] Levels: Viewer/Editor/Owner behaviours, teams, Auditor read-only, migration to Editor.
- [ ] OpenFGA on: levels and team grants answered by OpenFGA (fake evaluates computed relations).
- [ ] Sessions, limits, TOTP, Keycloak re-check and back-channel logout (see sessions reference).
- [ ] HTTPS state save/restore (unchanged folder not re-uploaded, unsafe archive refused, unreachable store still releases Caddy, first certificate saved).
- [ ] API documentation catalog updated for new routes.
- [ ] Full backend suite (Lapi: `python lapi_testing/run_backend_tests.py`, ~1450 tests, run in background).
- [ ] Frontend: `tsc --noEmit` and unit tests in Docker (`node:22-slim`, `npm ci`); compare failing test **names**
      with `main` (a known set already fails there) rather than the count.

## Manual checks
- [ ] Local Keycloak demo (`lapi_local_use/keycloak-demo`): alice admin, bob in group Finance, carol auditor
      (local demo test accounts only); first sign-in shows the tour; Access map shows "Editor via Finance";
      carol is read-only with no datasets; sign-out goes through Keycloak.
- [ ] Browser at desktop and 375 px (no horizontal page scroll); keyboard paths; screenshots sent to the user.

## Deploy (only after the user's explicit go-ahead for this deploy)
1. Bump the version files; commit.
2. Build images for linux/amd64 (api with the production build args, web), tag with the version, push to OCIR.
3. `terraform plan -var image_tag=<version> -out=<file>`; summarise resources (normally: instance + LB backends
   replaced); list **case-sensitive environment-variable changes**; anything unexpected → stop and ask.
4. Database changes: say exactly what the startup upgrade adds (tables/columns, additive only); any new DB user
   or destructive change needs explicit approval.
5. `terraform apply <file>`; if it fails half way, explain the outage and fix forward carefully (targeted apply).
6. Verify: HTTPS 200, HTTP redirects, certificate reused (same notBefore), all containers running, LB health OK
   (may need a minute), api logs without tracebacks, new routes answer 401 unauthenticated, deployed JS contains
   the new screens, version string. Update helper scripts that hold the instance OCID.
7. Push the branch, open/refresh the PR, report what is live and what is unverified.
