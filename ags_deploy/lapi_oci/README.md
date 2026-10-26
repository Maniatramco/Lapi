# Lapi on OCI Always Free

Lapi runs on its own OCI resources, separate from Aegis, using only Always Free shapes.

| Resource | Name | Size |
| --- | --- | --- |
| Compartment | `lapi` | |
| Network | `lapi-vcn` (10.60.0.0/16), `lapi-igw`, `lapi-public` | ports 22 and 80 open |
| VM | `lapi-vm`, Ubuntu 24.04 arm64 | VM.Standard.A1.Flex, 2 OCPU, 12 GB, 50 GB boot |
| Database | `lapidb` Always Free Autonomous Database | TLS, only `lapi-vm` IP allowed |

On the VM, Docker Compose runs `web`, `api`, `worker`, `qdrant` and `ollama`
(local `qwen3:4b` and `nomic-embed-text`, so no paid AI calls). Tables are
created by the backend in the `LAPI_OWNER` schema of `lapidb`.

## Provision and deploy

Open OCI Cloud Shell and run:

```sh
bash <(curl -fsSL https://raw.githubusercontent.com/Maniatramco/Lapi/lapi_sprint1/ags_deploy/lapi_oci/provision.sh)
```

The script first checks the whole tenancy stays within Always Free (A1 4 OCPU / 24 GB,
200 GB block storage, 2 free databases) and stops if not. It only creates resources in
the `lapi` compartment and reuses them on re-runs.

## Secrets

Nothing secret is committed. Generated values live only in:

- Cloud Shell `~/.lapi/` (SSH key, database ADMIN password)
- `lapi-vm:/opt/lapi/secrets/` (app DB password, master key, bootstrap token)

Read the first-admin bootstrap token from Cloud Shell:

```sh
ssh -i ~/.lapi/lapi_ssh ubuntu@$(cat ~/.lapi/public_ip) cat /opt/lapi/secrets/bootstrap_token
```

## Update after code changes

```sh
ssh -i ~/.lapi/lapi_ssh ubuntu@$(cat ~/.lapi/public_ip) \
  "cd /opt/lapi/app && git pull && PUBLIC_IP=$(cat ~/.lapi/public_ip) bash ags_deploy/lapi_oci/vm_up.sh"
```
