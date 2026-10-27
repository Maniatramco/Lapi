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

resource "oci_vault_secret" "db_password" {
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-db-admin-password"
  description    = "ADMIN password of lapidb; set the real value as a new version in the Console"
  secret_content {
    content_type = "BASE64"
    content      = base64encode("replace-in-console")
  }
  # The real password is added in the Console; Terraform must never overwrite it.
  lifecycle {
    ignore_changes = [secret_content]
  }
}
