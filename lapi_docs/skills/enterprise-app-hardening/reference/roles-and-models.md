# Workspace roles from Keycloak, and who chooses models

## The roles (all set in Keycloak, realm roles; Lapi never needs a per-person edit)
| Keycloak realm role | What the app grants | Stored in Lapi as |
|---|---|---|
| `<app>-administrator` | Everything, including **Manage workspace** (users, teams, Access map, storage, settings, model registration and Defaults, token usage, files & processing, workspace reset) | `users_tbl.role = 'administrator'` + OpenFGA `lapi:workspace#administrator` |
| `<app>-contributor` | **Owner on every dataset** and create / delete / restore datasets, dataset onboarding. **Not** Manage workspace, **not** model mapping | `workspace_contributor_tbl(user_id)` + OpenFGA `lapi:workspace#contributor` |
| `<app>-auditor` | Read-only view of people, access and activity; no dataset content | `workspace_role_tbl(role='auditor')` + OpenFGA `lapi:workspace#auditor` |
| none | Only the datasets shared with the person or their teams (Viewer / Editor / Owner) | `user_dataset_tbl`, `team_dataset_tbl` |

- Contributor is a **separate table** (not a value in `workspace_role_tbl`) so a person can be Auditor and
  Contributor at once. `ondelete=CASCADE` on the user FK. Created by `create_all` (no ALTER needed).
- Sync: `keycloak_auth._identity` reads `LAPI_KEYCLOAK_CONTRIBUTOR_ROLE` (default `lapi-contributor`) from realm and
  client roles in the ID and access tokens; `provision()` adds/removes the row at **every sign-in and every 5-minute
  re-check**; an administrator never also gets the contributor row. OpenFGA `_note_changes` must list the new model
  class so commits sync the tuple; `_reconcile(user)` must also read the `contributor` tuple.
- `dataset_access.manages_datasets(actor) = is_administrator or is_contributor`; used by `dataset_levels` and
  `dataset_ids` (contributor → `owner` on all live datasets), and `require_contributor()` replaces
  `require_admin()` in dataset create/delete/restore and agent onboarding.
- Route policy gets a **`contributor`** level (administrators or contributors) enforced centrally in `auth()`.
- `auth/me` and `/api/users` return `is_contributor`; UI labels "Contributor" in Users & passwords and the Access map
  (in-step check compares OpenFGA's contributor answer too).
- **"Let everyone play around"** = in Keycloak: Realm roles → create `lapi-contributor`; Realm settings → User
  registration → **Default roles** → Assign role → switch the filter to **"Filter by realm roles"** (it opens on
  client roles) → pick it. Remove it there to go back to per-dataset access.

## Who chooses models (the user's rule: "admin sets defaults for everything and does mapping")
- **Administrators** set workspace Default Chat / Extraction / Embedding / OCR models (Model Registration) and map
  extra models to datasets (Manage dataset → Models). Routes `PUT /api/datasets/{id}/models` and
  `POST /api/datasets/{id}/local-models` stay `admin`.
- **New datasets use the workspace Defaults automatically.** `POST /api/datasets/{id}/migrate-settings` checks
  `workspace_defaults.current()`: when embedding is pinned and chat + extraction Defaults are ready it saves
  **empty mappings** (`save_mappings(r, MappingInput())`), i.e. "use the Defaults". Only without Defaults does it fall
  back to the legacy import, and then **only for administrators** (others get 409 "An administrator needs to choose
  the Default … models").
  - Bug this fixed: the legacy import looked for models **owned by the caller** (`equivalent(owner, ...)`); for a
    Contributor it created private model copies from old settings, whose embedding clashed with the workspace
    Default → 400 "Datasets use the workspace Default embedding model…". Admins never saw it (they own the models).
- **Chat model picking is for everyone**: datasets report `chat_choices` = enabled mapped chat models + the
  workspace Default chat model (`routing_public`). Frontend `eligibleAgentModels()` prefers `chat_choices`, so a
  brand-new dataset still offers the Default. The backend already accepted the workspace Default in
  `resolve_model`.
- Manage dataset keeps `isAdmin={user.is_admin}` (mapping editor admin-only); dataset creation/deletion UI uses
  `is_admin || is_contributor`.

## Tests to copy (`lapi_testing/backend/test_route_policy.py`)
- Contributor owns every dataset, creates/deletes/restores, and gets 403 on users, access map, storage, token
  usage, teams, settings, models, admin documents.
- **Contributor Quick start end to end** with workspace Defaults that differ from legacy settings (the production
  case): create → migrate-settings 200 with `mappings == []`, no new models, upload, worker, chat with a picked
  model, template, extraction ready; `PUT /models` 403.
- Contributor before Defaults exist → 409 and no models created.
- `test_keycloak_auth.py`: role `lapi-contributor` adds the row; removing it in Keycloak removes it at next sign-in.
- `test_openfga_authz.py`: the contributor tuple appears and disappears with the row.
