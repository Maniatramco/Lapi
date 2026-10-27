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
  description = "Load balancer address: open http://<ip>, or point a DNS record here."
  value       = oci_load_balancer_load_balancer.lapi.ip_address_details[0].ip_address
}

output "database" {
  value = {
    name   = data.oci_database_autonomous_database.lapi.db_name
    vcn_id = oci_core_vcn.lapi.id
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
