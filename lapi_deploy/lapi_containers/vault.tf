# The master key that encrypts saved credentials, the database password and the
# first administrator's password live in OCI Vault. The app reads them at start-up with the VM's instance
# principal; neither is written to the VM's disk or to its metadata.
#
# Terraform state holds these values: keep state in a private, encrypted backend.

locals {
  create_vault = var.existing_vault_id == ""
  vault_id     = local.create_vault ? oci_kms_vault.lapi[0].id : var.existing_vault_id
  key_id       = local.create_vault ? oci_kms_key.lapi[0].id : var.existing_key_id
}

resource "oci_kms_vault" "lapi" {
  count          = local.create_vault ? 1 : 0
  compartment_id = var.compartment_ocid
  display_name   = "${var.name}-vault"
  vault_type     = "DEFAULT"
}

resource "oci_kms_key" "lapi" {
  count               = local.create_vault ? 1 : 0
  compartment_id      = var.compartment_ocid
  display_name        = "${var.name}-master-encryption-key"
  management_endpoint = oci_kms_vault.lapi[0].management_endpoint
  protection_mode     = "HSM"
  key_shape {
    algorithm = "AES"
    length    = 32
  }
}

# Fernet master key: 32 random bytes, URL-safe base64.
resource "random_bytes" "master_key" {
  length = 32
}

resource "random_password" "first_admin" {
  length      = 20
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
  special     = false
}

resource "oci_vault_secret" "first_admin" {
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-first-admin-password"
  description    = "Password of the first Lapi administrator (${var.admin_username}); read it in the Console"
  secret_content {
    content_type = "BASE64"
    content      = base64encode(random_password.first_admin.result)
  }
}

resource "oci_vault_secret" "master_key" {
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-app-master-key"
  description    = "Lapi credential master key (Fernet)"
  secret_content {
    content_type = "BASE64"
    content      = base64encode(replace(replace(random_bytes.master_key.base64, "+", "-"), "/", "_"))
  }
}

# Keycloak client secret: Terraform only creates the secret; paste the real value
# from Keycloak (Clients > lapi > Credentials) as a new version in the Console.
# With keycloak_hosted the secret is generated instead (keycloak.tf).
resource "oci_vault_secret" "keycloak_client" {
  count          = local.keycloak_secret && !var.keycloak_hosted ? 1 : 0
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-keycloak-client-secret"
  description    = "Client secret of the Keycloak client ${var.keycloak_client_id}; paste it in the Console"
  secret_content {
    content_type = "BASE64"
    content      = base64encode("replace-in-console")
  }
  lifecycle {
    ignore_changes = [secret_content, description]
  }
}

resource "oci_vault_secret" "db_password" {
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-db-admin-password"
  description    = "ADMIN password of lapidb (Vault-generated; copy it into lapidb's Administrator password)"
  secret_content {
    content_type = "BASE64"
    content      = base64encode("replace-in-console")
  }
  # Vault generates the real password (DBAAS_DEFAULT_PASSWORD template, enabled
  # outside Terraform); Terraform must never overwrite it or the generation setting.
  lifecycle {
    ignore_changes = [secret_content, enable_auto_generation, secret_generation_context, description, replication_config]
  }
}
