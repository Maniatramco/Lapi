# Lapi on OCI: Terraform

Lapi runs as containers on **OCI Container Instances**. There is no VM to manage.

| Piece | What holds it |
|---|---|
| web, api, worker | One container instance (`CI.Standard.E4.Flex`) in a private subnet, three containers sharing localhost |
| Public entry point | 10 Mbps flexible Load Balancer with a stable IP (HTTP; add a certificate for HTTPS) |
| Users, datasets, jobs, **vectors** | Existing Always Free **Autonomous AI Database 26ai** `lapidb`, read by Terraform, TLS (no Postgres, no Qdrant) |
| Uploaded documents | Object Storage bucket `lapi-documents`, prefix `lapi-documents/` |
| Settings, encrypted credentials, storage routes, archives | Same bucket, prefix `lapi-control/` (`AEGIS_CONTROL_STORE=oci`) |
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
cd ags_deploy\terraform
copy terraform.tfvars.example terraform.tfvars   # fill in OCIDs
terraform init
terraform apply                                  # image_tag empty: everything except the container instance
.\push-images.ps1 -Tag 26.1.12.19                # build and push lapi/api and lapi/web
terraform apply -var image_tag=26.1.12.19        # starts the container instance
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

## Limits

- **One container instance.** The api and worker share file locks through the
  instance's `scratch` volume, so do not run two instances against the same bucket.
- **HTTPS** is not configured yet: add a certificate and a port-443 listener to the
  load balancer, then set `COOKIE_SECURE` to `true`.
- **Database user.** The app connects as `ADMIN`. Create a dedicated schema user for
  production and change `ORACLE_USER` and the password secret.
- **Cost.** lapidb and a 10 Mbps load balancer are Always Free; Container Instances
  are billed per OCPU and GB of memory while running.
