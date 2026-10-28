# Hosted Keycloak (keycloak_hosted = true): sign-in for Lapi at https://sso.<load balancer IP>.sslip.io,
# in the same container instance, with its data in lapidb as the database user KEYCLOAK.
#
#   - image lapi/keycloak (lapi_deploy/keycloak, pushed by push-images.ps1 with the same tag)
#   - three generated Vault secrets: the KEYCLOAK database password, the Keycloak console
#     password (user kcadmin; read it in the Console) and the client secret Lapi and Keycloak share
#   - the realm "lapi" imported on first start (lapi_deploy/keycloak/realm-lapi.json)
#   - Caddy serves sso.* and reads the load balancer's PROXY protocol v2 header, so Lapi and
#     Keycloak see people's real addresses (sign-in limits, brute-force detection, audit)
#
# The api prepares the database user and hands Keycloak its secrets (keycloak_bootstrap.py);
# the keycloak container waits for that. The client secret reaches Keycloak as an environment
# variable at start-up, never through the realm file, so it is only in Vault and Terraform state.

# Always created (free), so push-images.ps1 pushes the image before keycloak_hosted is turned on.
resource "oci_artifacts_container_repository" "keycloak" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.name}/keycloak"
  is_public      = false
}

resource "random_password" "keycloak_db" {
  count       = var.keycloak_hosted ? 1 : 0
  length      = 24
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
  special     = false # Quoted inline in CREATE/ALTER USER: letters and digits only.
}

resource "random_password" "keycloak_admin" {
  count       = var.keycloak_hosted ? 1 : 0
  length      = 20
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
  special     = false
}

resource "random_password" "keycloak_client" {
  count   = var.keycloak_hosted ? 1 : 0
  length  = 40
  special = false
}

resource "oci_vault_secret" "keycloak_db_password" {
  count          = var.keycloak_hosted ? 1 : 0
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-keycloak-db-password"
  description    = "Password of the KEYCLOAK database user in lapidb (set by Lapi at start-up)"
  secret_content {
    content_type = "BASE64"
    content      = base64encode(random_password.keycloak_db[0].result)
  }
}

resource "oci_vault_secret" "keycloak_admin_password" {
  count          = var.keycloak_hosted ? 1 : 0
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-keycloak-admin-password"
  description    = "Password of kcadmin, the Keycloak console administrator (master realm); read it in the Console"
  secret_content {
    content_type = "BASE64"
    content      = base64encode(random_password.keycloak_admin[0].result)
  }
}

# Separate from keycloak_client (vault.tf), whose value is pasted by hand for an external Keycloak.
resource "oci_vault_secret" "keycloak_hosted_client" {
  count          = var.keycloak_hosted ? 1 : 0
  compartment_id = var.compartment_ocid
  vault_id       = local.vault_id
  key_id         = local.key_id
  secret_name    = "${var.name}-keycloak-lapi-client-secret"
  description    = "Client secret of the client lapi in the hosted Keycloak (generated)"
  secret_content {
    content_type = "BASE64"
    content      = base64encode(random_password.keycloak_client[0].result)
  }
}

locals {
  sso_hostname   = var.keycloak_hostname != "" ? var.keycloak_hostname : "sso.${local.lb_ip}.sslip.io"
  keycloak_image = "${local.registry}/${var.name}/keycloak:${var.image_tag}"
  # PROXY protocol v2 from both load balancer listeners to Caddy (loadbalancer.tf).
  proxy_protocol = var.keycloak_hosted && var.https
  hosted_secret_ids = var.keycloak_hosted ? [
    oci_vault_secret.keycloak_db_password[0].id,
    oci_vault_secret.keycloak_admin_password[0].id,
    oci_vault_secret.keycloak_hosted_client[0].id,
  ] : []

  # Caddy global options. The load balancer's TCP health checks open a connection without a
  # PROXY header: from the load balancer's subnet ("allow") the header is used when present and
  # optional otherwise; a header from any other address is refused (fallback_policy reject).
  caddy_global = local.proxy_protocol ? local.caddy_proxy_protocol : ""
  # Inside Caddy's global options block, so every line gets one more tab.
  caddy_proxy_protocol = join("", [for line in split("\n", trimsuffix(local.caddy_servers, "\n")) : "\t${line}\n"])
  caddy_servers        = <<-EOT
    servers {
    	listener_wrappers {
    		proxy_protocol {
    			timeout 5s
    			allow ${local.public_cidr}
    			fallback_policy reject
    		}
    		tls
    	}
    }
  EOT
  # The admin console (/admin) stays reachable: it needs kcadmin's password from Vault and
  # Keycloak's own brute-force protection applies. To close it, add before reverse_proxy:
  #   @console path /admin /admin/*
  #   respond @console 404
  caddy_sso      = var.keycloak_hosted ? "\n${trimsuffix(local.caddy_sso_site, "\n")}" : ""
  caddy_sso_site = <<-EOT
    ${local.sso_hostname} {
    	encode zstd gzip
    	reverse_proxy 127.0.0.1:8180
    }
  EOT

  # Only the api creates the database user and hands Keycloak its secrets.
  keycloak_bootstrap_env = var.keycloak_hosted ? {
    LAPI_KEYCLOAK_DB_PASSWORD_SECRET_OCID    = oci_vault_secret.keycloak_db_password[0].id
    LAPI_KEYCLOAK_ADMIN_PASSWORD_SECRET_OCID = oci_vault_secret.keycloak_admin_password[0].id
    LAPI_KEYCLOAK_SECRETS_DIR                = "/data/keycloak-secrets"
  } : {}

  # ${LAPI_CLIENT_SECRET} is left for Keycloak to fill in from its environment at import.
  keycloak_realm_json = templatefile("${path.module}/../keycloak/realm-lapi.json", {
    lapi_url = local.public_url
  })

  keycloak_container_env = {
    # Autonomous Database over TLS without a wallet (Java's own CA certificates), LOW service.
    KC_DB_URL           = "jdbc:oracle:thin:@${replace(local.db_dsn, " ", "")}"
    KC_DB_USERNAME      = "KEYCLOAK"
    KC_DB_POOL_MAX_SIZE = "10" # Lapi shares the database's session limit.
    KC_HOSTNAME         = "https://${local.sso_hostname}"
    # Caddy (on localhost) sets X-Forwarded-For/-Proto; nobody else can reach port 8180.
    KC_PROXY_HEADERS            = "xforwarded"
    KC_PROXY_TRUSTED_ADDRESSES  = "127.0.0.1"
    KC_HTTP_ENABLED             = "true"
    KC_HTTP_HOST                = "127.0.0.1"
    KC_HTTP_PORT                = "8180"
    KC_HTTP_MANAGEMENT_PORT     = "9000"
    KC_BOOTSTRAP_ADMIN_USERNAME = "kcadmin"
    KC_LOG_LEVEL                = "INFO,oracle.jdbc:warn"
    # Heap at most 60% of the container's memory limit (keycloak_memory_gbs): about 1.2 GB of 2.
    JAVA_OPTS_KC_HEAP = "-XX:MaxRAMPercentage=60 -XX:InitialRAMPercentage=25 -XX:MaxHeapFreeRatio=30"
  }
}
