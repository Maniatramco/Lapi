# Lapi on OCI: Terraform

Lapi runs as containers on **OCI Container Instances**. There is no VM to manage.

| Piece | What holds it |
|---|---|
| web, api, worker, Ollama | One container instance (`CI.Standard.E4.Flex`) in a private subnet, four containers sharing localhost; Ollama serves the local `qwen3:4b` and `nomic-embed-text` models (pulled at start-up) |
| Public entry point | 10 Mbps flexible Load Balancer with a stable IP (HTTP; add a certificate for HTTPS) |
| Users, datasets, jobs, **vectors** | Existing Always Free **Autonomous AI Database 26ai** `lapidb`, read by Terraform, TLS (no Postgres, no Qdrant) |
| Uploaded documents | Object Storage bucket `lapi-documents`, prefix `lapi-documents/` |
| Settings, encrypted credentials, storage routes, archives | Same bucket, prefix `lapi-control/` (`LAPI_CONTROL_STORE=oci`) |
| Credential master key, database password | OCI Vault secrets, read with the container instance's resource principal |
| Images | OCIR repositories `lapi/api`, `lapi/web` |
| File locks, caches | The instance's `scratch` volume (temporary by design) |

No API key, password or master key is stored in a container, an image or this
repository. Terraform state does contain the generated master key and database
password, so keep state private (for example in an OCI Object Storage backend).

## Files

- `network.tf`: VCN; public subnet for the load balancer; private subnet for the containers with NAT and service gateways.
- `loadbalancer.tf`: the load balancer, forwarding port 80 to the web container.
- `database.tf`: reads the existing `lapidb` (`existing_db_id`).
- `storage.tf`: the bucket.
- `vault.tf`: Vault and key (or reuse existing ones) plus the two secrets.
- `iam.tf`: dynamic group for Lapi's container instances and its policy.
- `containers.tf`: OCIR repositories and the container instance.
- `push-images.ps1`: build and push the two images.

## Deploy

Needs Terraform 1.6+, Docker, an `~/.oci/config` allowed to manage these
resources and IAM, and an OCI auth token for OCIR.

```powershell
cd lapi_deploy\lapi_containers
copy terraform.tfvars.example terraform.tfvars   # fill in OCIDs
terraform init
terraform apply                                  # image_tag empty: everything except the container instance
.\push-images.ps1 -Tag 26.1.16.0                # build and push lapi/api and lapi/web
terraform apply -var image_tag=26.1.16.0        # starts the container instance
terraform output public_ip
```

Before the containers start, two one-time steps for `lapidb`:

1. **Password.** In the Console open Vault `lapi-vault` > Secrets >
   `lapi-db-admin-password` > Create secret version, and enter lapidb's ADMIN
   password. Terraform never overwrites it.
2. **Access list.** lapidb (Always Free) has no private endpoint. Add the VCN
   (`terraform output database` shows `vcn_id`) to lapidb's access control list,
   keeping the existing entries. The containers reach it through the service gateway.

The first administrator (`admin_username`, default `admin`) is created once when
the api starts. Its generated password is the Vault secret `lapi-first-admin-password`
(Console: Identity & Security > Vault > lapi-vault > Secrets > the secret >
Version > View secret contents). Change it after signing in.

## Sign-in with Keycloak, permissions with OpenFGA

OpenFGA runs as a container in the same instance (in-memory store, localhost only)
and answers every permission check; the api rebuilds its tuples from lapidb whenever
it starts or OpenFGA restarts. It needs no setup.

Keycloak is yours (not deployed here). To sign people in with it:

1. In your realm, create an OpenID Connect client `lapi`: Standard flow on,
   Client authentication on, PKCE method S256.
2. Create the realm role `lapi-administrator` and give it to Lapi's administrators.
3. Set `keycloak_url`, `keycloak_realm` and `keycloak_client_id` in
   `terraform.tfvars` and apply. Terraform creates the empty Vault secret
   `lapi-keycloak-client-secret` and outputs `keycloak_redirect_uri`.
4. Paste the client secret (Clients > lapi > Credentials) into that Vault secret
   as a new version in the Console.
5. In the Keycloak client, add `keycloak_redirect_uri` as a Valid redirect URI and
   `<public_url>/` as a Valid post logout redirect URI. Lapi reads the secret at
   sign-in, so a new secret version takes effect within five minutes, no restart.

Accounts are created at each person's first Keycloak sign-in; their role follows
`lapi-administrator` at every sign-in. Lapi passwords stay only for local
administrators such as `admin` (break-glass). Lapi sessions last 12 hours, so
disabling someone in Keycloak takes effect at their next sign-in: delete their
Lapi account to end access at once. Keycloak should be served over HTTPS.

## Limits

- **One container instance.** The api and worker share file locks through the
  instance's `scratch` volume, so do not run two instances against the same bucket.
- **HTTPS** (on by default): Caddy in the container instance serves
  `https://lapi.<load balancer IP>.sslip.io` with a Let's Encrypt certificate and
  redirects port 80 to it. The api keeps the certificate in the control bucket
  (`tls/caddy-data.tar.gz`) so deployments reuse it; Let's Encrypt allows five new
  certificates a week for one name. Use `https_hostname` for your own domain (point
  its DNS A record at the load balancer first), or `https = false` for plain HTTP.
- **Database user.** The app connects as `ADMIN`. Create a dedicated schema user for
  production and change `ORACLE_USER` and the password secret.
- **Cost.** lapidb and a 10 Mbps load balancer are Always Free; Container Instances
  are billed per OCPU and GB of memory while running.
