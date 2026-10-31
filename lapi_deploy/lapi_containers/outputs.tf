output "registry" {
  description = "Push images here (see push-images.ps1)."
  value       = local.registry
}

output "image_repositories" {
  value = {
    api      = "${local.registry}/${var.name}/api"
    web      = "${local.registry}/${var.name}/web"
    keycloak = "${local.registry}/${var.name}/keycloak"
  }
}

output "public_ip" {
  description = "Load balancer address: point a DNS record here when using your own https_hostname."
  value       = oci_load_balancer_load_balancer.lapi.ip_address_details[0].ip_address
}

output "url" {
  description = "Where people open Lapi."
  value       = local.public_url
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

output "keycloak_redirect_uri" {
  description = "Add this as a Valid redirect URI of the Keycloak client (and <public_url>/ as a post-logout redirect URI)."
  value       = local.keycloak ? "${local.public_url}/api/auth/keycloak/callback" : null
}

output "keycloak_console" {
  description = "Hosted Keycloak's admin console: sign in as kcadmin with the password in the Vault secret keycloak_admin."
  value       = var.keycloak_hosted ? "https://${local.sso_hostname}/admin/master/console/#/lapi" : null
}

output "secrets" {
  description = "Vault secret OCIDs (values are never output)."
  value = {
    master_key     = oci_vault_secret.master_key.id
    db_password    = oci_vault_secret.db_password.id
    first_admin    = oci_vault_secret.first_admin.id
    keycloak       = local.keycloak_secret ? local.keycloak_secret_id : null
    keycloak_admin = var.keycloak_hosted ? oci_vault_secret.keycloak_admin_password[0].id : null
    keycloak_db    = var.keycloak_hosted ? oci_vault_secret.keycloak_db_password[0].id : null
  }
}
