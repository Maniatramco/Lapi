# Lapi

Secure data lakehouse and AI platform: dataset onboarding, document extraction and review, and a grounded Lapi Agent with hybrid retrieval, reranking and cited answers.

**Working branch: `lapi_sprint1`. Current version: `v26.1.16.38`.**

## Repository layout

| Folder | Contents |
| --- | --- |
| `lapi_backend/` | FastAPI API and worker (`lapi_app` package), model providers, agents |
| `lapi_frontend/` | Next.js web application |
| `lapi_database/` | Oracle table definitions and read-only checks |
| `lapi_deploy/` | Deployment tools; `lapi_containers/` is the live OCI deployment (Terraform) |
| `lapi_local_use/` | Local Docker Compose setups and helper scripts |
| `lapi_testing/` | Backend, frontend and browser tests |
| `lapi_docs/` | Architecture and deployment documents |
| `delete/` | Retired files kept for reference; not built or tested |

## Live deployment

Lapi runs on OCI Container Instances in its own `lapi` compartment, with no VM:
one container instance (web, api, worker and Ollama with the local `qwen3:4b` and
`nomic-embed-text` models) behind a load balancer, the `lapidb` Always Free
Autonomous Database for data and vectors, Object Storage for files and Lapi's own
settings, and OCI Vault for the master key and passwords. Everything is defined in
Terraform: see [`lapi_deploy/lapi_containers/README.md`](lapi_deploy/lapi_containers/README.md).
The earlier VM setup (`lapi_oci`) is retired to `delete/`.

## Local development

```sh
./lapi_local_use/lapi_scripts/setup.sh
docker compose --project-directory . --env-file .env -f lapi_local_use/compose.yaml up --build -d
```

More options are in [`lapi_local_use/README.md`](lapi_local_use/README.md).

## Versions

Each release updates `lapi_frontend/app/application-version.json` (shown in the footer and About screen), [`CHANGELOG.md`](CHANGELOG.md) and the current version above.
