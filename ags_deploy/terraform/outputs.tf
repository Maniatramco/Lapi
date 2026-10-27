output "registry" {
  description = "Push images here (see push-images.ps1)."
  value       = local.registry
}

output "image_repositories" {
  value = {
    api = "${local.registry}/${var.name}/api"
    web = "${local.registry}/${var.name}/web"
  }
}

output "public_ip" {
  description = "Open http://<ip> (or point site_address's DNS record here). Empty until image_tag is set."
  value       = length(data.oci_core_vnic.lapi) > 0 ? data.oci_core_vnic.lapi[0].public_ip_address : ""
}

output "database" {
  value = {
    name             = oci_database_autonomous_database.lapi.db_name
    private_endpoint = oci_database_autonomous_database.lapi.private_endpoint
  }
}

output "bucket" {
  value = oci_objectstorage_bucket.lapi.name
}

output "secrets" {
  description = "Vault secret OCIDs (values are never output)."
  value = {
    master_key  = oci_vault_secret.master_key.id
    db_password = oci_vault_secret.db_password.id
    first_admin = oci_vault_secret.first_admin.id
  }
}
