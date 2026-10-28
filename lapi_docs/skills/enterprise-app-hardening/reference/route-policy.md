# Access levels and the route policy

## Levels (per dataset, for people and teams)

| Level | Can |
|---|---|
| **Viewer** | Open the dataset, read documents and results, chat, export what they can read |
| **Editor** | Viewer + upload, reindex, re-extract, delete documents, keep temporary uploads, create/edit prompts, run/review/re-run extractions, connect cloud storage and import, retry or cancel other people's jobs |
| **Owner** | Editor + rename/describe the dataset, edit its instructions and prompt guide, manage its members (people and teams) |
| **Administrator** (workspace) | Everything: every dataset, people, roles, teams, models, mappings, activation, deletion, storage, settings |
| **Auditor** (workspace) | Read people, roles, the Access map and teams; no dataset content; changes nothing |
| **Contributor** (workspace, Keycloak `<app>-contributor`) | Owner on every dataset + create/delete/restore datasets and dataset onboarding; no Manage workspace, no model mapping (see `roles-and-models.md`) |

Route policy level **`contributor`** = administrators or contributors (dataset create/delete/trash/restore,
`status`, `migrate-settings`, `assign-documents`, agent onboarding). `PUT /datasets/{id}/models` and
`local-models` stay `admin`.

Rules that matter:
- Effective level = the highest of the person's own grant and their teams' grants.
- When introducing levels, **migrate every existing grant to Editor** (that is what it could already do) and
  make new grants default to Viewer. Bootstrap grants for dataset owners become Owner.
- Model mappings, dataset activation and deletion stayed administrator-only even for Owners (cost/infra).
- Admins cannot be added as dataset members (they already have everything): return 400.

## Enforcement pattern

1. `dataset_access.py`: `RANK = {viewer:1, editor:2, owner:3}`, `dataset_levels(actor, session)` (OpenFGA
   `list-objects` per level, or DB own + team grants), `level_for`, `require_level(actor, dataset_id, needed)`
   → 404 if no access, 403 with a plain message ("This needs Editor access to the dataset; you have Viewer access.
   Ask the dataset owner or an administrator.") if too low. Trusted internal calls (no HTTP actor) pass.
2. `get_record(id, actor, kind, level='viewer')`: after the existing visibility check, require the level on the
   record's dataset (`record_dataset(record)`; personal records stay owner-only).
3. Change every write route: `level='editor'` / `require_level(..., 'owner')`. Jobs: `require_job_change`
   (Editor, or the person who started it). Connectors: one `authorize()` function → raise to Editor.
4. `GET /api/datasets` returns `my_access` per dataset so screens hide actions (the API still enforces).

## Route policy table (`route_policy.py`)

```python
POLICY = {('GET', '/api/auth/status'): 'public', ('POST', '/api/documents/upload'): 'editor',
          ('PATCH', '/api/datasets/{id}'): 'owner', ('GET', '/api/users'): 'audit', ('POST', '/api/users'): 'admin', ...}

def check(method, path, actor):
    policy = POLICY.get((method, path))
    if policy is None: raise HTTPException(403, 'This action is not available.')   # fail closed
    if policy == 'admin' and not core.is_administrator(actor): raise HTTPException(403, ...)
    if policy == 'audit' and not (core.is_administrator(actor) or is_auditor(actor)): raise HTTPException(403, ...)
```

In `auth()` (after authenticating and setting the request actor):
```python
route = request.scope.get('route')
await run_in_threadpool(route_policy.check, 'GET' if request.method == 'HEAD' else request.method,
                        getattr(route, 'path', request.url.path), owner)
```
This replaced Lapi's old "writes under these path prefixes are admin-only" rule. Note that modules whose own
dependency requires admin (e.g. `administrator`) must be relaxed to admin-or-auditor for `audit` routes.

## The test that keeps it honest

```python
def api_routes(routes):
    for route in routes:
        if type(route).__name__ == '_IncludedRouter':          # FastAPI 0.14x lazy include_router
            yield from api_routes(route.original_router.routes)
        elif isinstance(route, APIRoute) and route.path.startswith('/api'):
            for method in route.methods - {'HEAD'}: yield method, route.path

live = set(api_routes(main.app.routes))
assert not live - POLICY.keys()      # every route classified
assert not POLICY.keys() - live      # no stale entries
```
Add behaviour tests: Viewer refused upload/delete/reindex/template (403), Editor allowed; Owner can rename and
manage members but not model mappings or /api/users; team grant gives access and removing it removes access;
Auditor reads /api/users and /api/access-map (`can_edit: false`) but cannot PUT and sees no datasets; migration
turns NULL levels into `editor`; Keycloak groups sync into team memberships.

## Fake OpenFGA for tests

The fake must evaluate the model, not just stored tuples:
```python
def has(tuples, user, relation, obj):
    if (user, relation, obj) in tuples: return True
    teams = {o for u, r, o in tuples if u == user and r == 'member' and o.startswith('team:')}
    if any((team + '#member', relation, obj) in tuples for team in teams): return True
    stronger = {'viewer': 'editor', 'editor': 'owner'}.get(relation)
    return bool(stronger and obj.startswith('dataset:') and has(tuples, user, stronger, obj))
```
Use it for both `check` and `list-objects`. Lapi's version: `lapi_testing/backend/test_openfga_authz.py`.
