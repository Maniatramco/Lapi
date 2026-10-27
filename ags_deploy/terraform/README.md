# Lapi on OCI: Terraform

Lapi runs as containers on **OCI Container Instances**. There is no VM to manage.

| Piece | What holds it |
|---|---|
| web, api, worker, HTTPS proxy | One container instance (`CI.Standard.E4.Flex`), four containers sharing localhost |
| Users, datasets, jobs, **vectors** | Oracle **Autonomous AI Database 26ai**, private endpoint, TLS (no Postgres, no Qdrant) |
| Uploaded documents | Object Storage bucket `lapi-documents`, prefix `lapi-documents/` |
| Settings, encrypted credentials, storage routes, archives | Same bucket, prefix `lapi-control/` (`AEGIS_CONTROL_STORE=oci`) |
| Credential master key, database password | OCI Vault secrets, read with the container instance's resource principal |
| Images | OCIR repositories `lapi/api`, `lapi/web` |
| File locks, caches | The instance's `scratch` volume (temporary by design) |

No API key, password or master key is stored in a container, an image or this
repository. Terraform state does contain the generated master key and database
password, so keep state private (for example in an OCI Object Storage backend).

## Files

- `network.tf`: VCN, public subnet (ports 80/443 only), private subnet for the database.
- `database.tf`: Autonomous AI Database with a private endpoint.
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

The first administrator (`admin_username`, default `admin`) is created once when
the api starts. Its generated password is the Vault secret `lapi-first-admin-password`
(Console: Identity & Security > Vault > lapi-vault > Secrets > the secret >
Version > View secret contents). Change it after signing in.

## Limits

- **One container instance.** The api and worker share file locks through the
  instance's `scratch` volume, so do not run two instances against the same bucket.
- **Public IP changes** when the container instance is replaced. For a stable address
  or a domain, put an OCI Load Balancer in front, or update the DNS record.
- **Database user.** The app connects as `ADMIN`. Create a dedicated schema user for
  production and change `ORACLE_USER` and the password secret.
- **Cost.** Autonomous AI Database is billed per ECPU (minimum 2); Container
  Instances per OCPU and GB of memory while running.
