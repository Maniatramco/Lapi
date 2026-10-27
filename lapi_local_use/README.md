# Local development and testing

Laptop runtime Compose configurations, environment templates and launch helpers
live here. Tests and QA tools live in `../lapi_testing/`. OCI installation and release tools stay in `../lapi_deploy/`.
Run the commands below from the repository root. `--project-directory .` keeps
build contexts, secrets, wallet mounts and storage paths anchored to that root.
Existing private `.env`, `.env.oracle`, `secrets/`, data and model directories
remain in their existing locations; they are not committed.

```text
lapi_local_use/
  compose*.yaml                 Local runtime configurations
  .env.example                 Local PostgreSQL configuration template
  .env.oracle.example          Local Oracle/Ollama configuration template
  Lapi-local.code-workspace    VS Code workspace, opening the repository root
  lapi_scripts/                 Local setup, launch, checks, backup and recovery helpers
  lapi_database/                Local Oracle Free setup and SQLAlchemy DDL generator
  lapi_docker/                  Oracle Free startup and health-check support
  lapi_kubernetes/              Alternative self-hosted Kubernetes CPU/GPU manifests
```

Default Docker development environment:

```sh
./lapi_local_use/lapi_scripts/setup.sh
docker compose --project-directory . --env-file .env -f lapi_local_use/compose.yaml up --build -d
```

Windows Oracle/Ollama launcher:

```powershell
./lapi_local_use/lapi_scripts/start-oracle.ps1
```

Create the first administrator once the API is running. There is no setup screen
or setup token; this only works while no account exists. The scripts prompt for
the username and password and pass them through stdin:

```sh
./lapi_local_use/lapi_scripts/create-admin.sh      # or create-admin.ps1 on Windows
```

They target the Oracle Compose configuration, like `create-colleague`. For any
other deployment, run the module inside the API container and type the JSON on stdin:

```sh
docker compose --project-directory . --env-file .env -f lapi_local_use/compose.yaml exec -T api python -m lapi_app.create_admin
```

### OCI deployment

Lapi runs on OCI Container Instances with no VM: data and vectors in Autonomous AI
Database, files and control state in Object Storage, the master key and database
password in OCI Vault. See [lapi_deploy/lapi_containers](../lapi_deploy/lapi_containers/README.md).

Existing laptop configuration with OCI credentials and local GPU inference:

```sh
docker compose --project-directory . --env-file .env.oracle -f lapi_local_use/compose.oracle.yaml -f lapi_local_use/compose.gpu.yaml -f lapi_local_use/compose.oracle-client.yaml -f lapi_local_use/compose.agents-low-memory.yaml -f lapi_local_use/compose.oci-storage.yaml ps
```

Use the same arguments for subsequent Docker operations. The Oracle client
overlay is optional and provides only loopback access to the local Oracle service.
The local database services are not the OKE application deployment.

Native development uses `lapi_scripts/windows-dev.py` in this folder. Open
`Lapi-local.code-workspace` for the Windows launch tasks. Automated tests,
manual QA, fictional fixtures and test container support are grouped in
[`../lapi_testing/`](../lapi_testing/README.md). CI combines this folder's
`compose.yaml` with `../lapi_testing/compose.test.yaml` and disposable mock data.
Never apply that test overlay to a real workspace.

The optional `lapi_kubernetes/` configuration uses Oracle Free, Qdrant and Ollama.
Render it with `./lapi_local_use/lapi_scripts/render-kubernetes.ps1 -Hardware Cpu`
from the repository root. It differs from the live OCI Autonomous Database
installation. The renderer writes manifests without applying them.

## Local database tools

`lapi_database/` in this local folder contains the optional Oracle Free
`LAPI_OWNER`/`FREEPDB1` owner setup, the twelve-table SQL installer and the
SQLAlchemy-based source DDL generator. These are local development tools.
The live OCI schema and read-only checks are maintained separately in the
repository-root `lapi_database/` folder.

From the repository root, generate only the local SQL files with:

```sh
python lapi_local_use/lapi_database/generate_tables.py
```

The generator writes `lapi_local_use/lapi_database/lapi_tables/` and its local
`install.sql`. It does not connect to OCI or write the live schema reference.
For an empty local Oracle Free schema, connect as `LAPI_OWNER` in `FREEPDB1`
and run `@lapi_local_use/lapi_database/install.sql`. Existing local credentials
remain under the repository's private `secrets/oracle/` directory.

## Local legacy owner migration

This is a one-time copy, not a rename or destructive move. The source `LAPI`
schema is retained. Application users, password hashes, sessions, IDs, versions,
timestamps, status/error fields and storage references are compared exactly before
the target transaction commits. Actual row contents and credentials are not logged.

1. Finish/cancel active jobs and stop application writes. Stop web, API and worker.
2. Create `LAPI_OWNER` using the Oracle startup script or `lapi_local_use/lapi_database/lapi_schema/create_owner.py`.
3. Build the updated backend image and run the migration against an **empty** target:

```powershell
docker compose --project-directory . --env-file .env.oracle -f lapi_local_use/compose.oracle.yaml -f lapi_local_use/compose.gpu.yaml -f lapi_local_use/compose.oracle-client.yaml build api worker
docker compose --project-directory . --env-file .env.oracle -f lapi_local_use/compose.oracle.yaml -f lapi_local_use/compose.gpu.yaml -f lapi_local_use/compose.oracle-client.yaml stop web api worker
docker compose --project-directory . --env-file .env.oracle -f lapi_local_use/compose.oracle.yaml -f lapi_local_use/compose.gpu.yaml -f lapi_local_use/compose.oracle-client.yaml run --rm --no-deps api python -m lapi_app.migrate_owner --source LAPI
docker compose --project-directory . --env-file .env.oracle -f lapi_local_use/compose.oracle.yaml -f lapi_local_use/compose.gpu.yaml -f lapi_local_use/compose.oracle-client.yaml up -d --no-deps --wait api worker web
```

Omit the GPU override for CPU machines. The migration implementation lives in
`lapi_backend/lapi_app/migrate_owner.py` so the identical API image can run it under Docker
or as a Kubernetes maintenance Job, with the same storage and secrets mounted.
It refuses a nonempty target or active jobs. Oracle DDL can leave empty tables
after failure; the data-copy transaction itself rolls back on verification errors.
Review rows are backfilled from retained reviewed JSON versions.

Fresh installations create the new schema directly; they do not need this copy.
Do not rerun it against the live migrated schema. There is no automatic migration
of an existing Oracle cluster during startup.

The old owner is a snapshot, not a continuously synchronized rollback database.
Before rolling back after new writes, plan how to retain those writes. Immediately
after migration, rollback can restart the **previous backend image** with its
previous `ORACLE_USER=LAPI` configuration and unchanged storage. The new image
uses renamed tables and must not be pointed at the old schema as a rollback.

Historical `created_by` / `updated_by` were not recorded and remain NULL, with
`created_via=legacy` and `updated_via=migration`. Legacy accounts/sessions had no
creation timestamps; their new audit timestamps mark import time. Historical
review actors/times are recovered from review JSON when available.
