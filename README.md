# Lapi

Secure data lakehouse and AI platform: dataset onboarding, document extraction and review, and a grounded Lapi Agent with hybrid retrieval, reranking and cited answers.

**Working branch: `lapi_sprint1`. Current version: `v26.1.13.1`.**

## Repository layout

| Folder | Contents |
| --- | --- |
| `lapi_backend/` | FastAPI API and worker (`lapi_app` package), model providers, agents |
| `lapi_frontend/` | Next.js web application |
| `lapi_database/` | Oracle table definitions and read-only checks |
| `lapi_deploy/` | Deployment tools; `lapi_oci/` is the live Always Free deployment |
| `lapi_local_use/` | Local Docker Compose setups and helper scripts |
| `lapi_testing/` | Backend, frontend and browser tests |
| `lapi_docs/` | Architecture and deployment documents |
| `delete/` | Retired files kept for reference; not built or tested |

## Live deployment

Lapi runs on OCI Always Free in its own `lapi` compartment: `lapi-vm` (Ampere A1, 2 OCPU / 12 GB) and the `lapidb` Autonomous Database. See [`lapi_deploy/lapi_oci/README.md`](lapi_deploy/lapi_oci/README.md) to provision, update or find the private secrets. No secrets are stored in this repository.

## Local development

```sh
./lapi_local_use/lapi_scripts/setup.sh
docker compose --project-directory . --env-file .env -f lapi_local_use/compose.yaml up --build -d
```

More options are in [`lapi_local_use/README.md`](lapi_local_use/README.md).

## Versions

Each release updates `lapi_frontend/app/application-version.json` (shown in the footer and About screen), [`CHANGELOG.md`](CHANGELOG.md) and the current version above.
