# The container instance's own identity (resource principal): read its two Vault
# secrets, use its bucket, and pull its images. No API key exists anywhere.

data "oci_identity_compartment" "lapi" {
  id = var.compartment_ocid
}

locals {
  compartment_name = data.oci_identity_compartment.lapi.name
  # Keycloak client secret (external or hosted) and the hosted Keycloak's own secrets (keycloak.tf).
  readable_keycloak_secrets = concat(local.keycloak_secret ? [local.keycloak_secret_id] : [], local.hosted_secret_ids)
}

resource "oci_identity_dynamic_group" "containers" {
  compartment_id = var.tenancy_ocid
  name           = "${var.name}-containers"
  description    = "Lapi container instances"
  matching_rule  = "ALL {resource.type = 'computecontainerinstance', resource.compartment.id = '${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "containers" {
  compartment_id = var.compartment_ocid
  name           = "${var.name}-containers"
  description    = "Lapi containers read their secrets, use their bucket and pull their images"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.containers.name} to read secret-bundles in compartment ${local.compartment_name} where any {target.secret.id = '${oci_vault_secret.master_key.id}', target.secret.id = '${oci_vault_secret.db_password.id}', target.secret.id = '${oci_vault_secret.first_admin.id}'${join("", [for id in local.readable_keycloak_secrets : ", target.secret.id = '${id}'"])}}",
    "Allow dynamic-group ${oci_identity_dynamic_group.containers.name} to read buckets in compartment ${local.compartment_name} where target.bucket.name = '${oci_objectstorage_bucket.lapi.name}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.containers.name} to manage objects in compartment ${local.compartment_name} where target.bucket.name = '${oci_objectstorage_bucket.lapi.name}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.containers.name} to read objectstorage-namespaces in compartment ${local.compartment_name}",
    "Allow any-user to read repos in compartment ${local.compartment_name} where all {request.principal.type = 'computecontainerinstance', request.principal.compartment.id = '${var.compartment_ocid}'}",
  ]
}
