# Lapi on OCI Container Instances: no VM. One container instance in the private
# subnet runs web, api, worker, ollama and openfga behind the load balancer (loadbalancer.tf).
# Containers in one instance share localhost and the
# "scratch" volume, which holds only file locks and caches; everything that must
# survive a restart is in Autonomous AI Database, Object Storage and Vault.
#
# Two-step first deployment: apply with image_tag = "" (creates everything except
# the container instance), push images (push-images.ps1), apply with image_tag set.

resource "oci_artifacts_container_repository" "api" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.name}/api"
  is_public      = false
}

resource "oci_artifacts_container_repository" "web" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.name}/web"
  is_public      = false
}

locals {
  # keycloak_hosted (keycloak.tf) points Lapi at the Keycloak in this instance.
  keycloak_url       = var.keycloak_hosted ? "https://${local.sso_hostname}" : var.keycloak_url
  keycloak_realm     = var.keycloak_hosted ? "lapi" : var.keycloak_realm
  keycloak_client_id = var.keycloak_hosted ? "lapi" : var.keycloak_client_id
  keycloak           = local.keycloak_url != ""
  keycloak_secret    = local.keycloak && (var.keycloak_hosted || var.keycloak_confidential_client)
  keycloak_secret_id = var.keycloak_hosted ? oci_vault_secret.keycloak_hosted_client[0].id : local.keycloak_secret ? oci_vault_secret.keycloak_client[0].id : null
  lb_ip              = oci_load_balancer_load_balancer.lapi.ip_address_details[0].ip_address
  https_hostname     = var.https_hostname != "" ? var.https_hostname : "lapi.${local.lb_ip}.sslip.io"
  public_url         = trimsuffix(var.public_url != "" ? var.public_url : var.https ? "https://${local.https_hostname}" : "http://${local.lb_ip}", "/")
  # Caddy terminates HTTPS on 443, redirects port 80 (except Let's Encrypt's checks) and
  # forwards to web on 3000. Its certificate is saved and restored by the api (tls_state.py).
  # With keycloak_hosted it also reads the load balancer's PROXY header and serves sso.* (keycloak.tf).
  caddyfile = <<-EOT
    {
    	admin off
    ${local.caddy_global}}
    ${local.https_hostname} {
    	encode zstd gzip
    	# Pages are re-checked on every visit so a new release shows at once; the versioned
    	# /_next/static files keep their long cache. ">" applies it after the web server's own header.
    	@pages not path /_next/static/* /api/*
    	header @pages >Cache-Control "no-cache"
    	reverse_proxy 127.0.0.1:3000
    }
    http:// {
    	redir https://${local.https_hostname}{uri} permanent
    }${local.caddy_sso}
  EOT
  # Sign-in through Keycloak (keycloak_auth.py); empty keeps Lapi's password sign-in.
  keycloak_env = local.keycloak ? merge({
    LAPI_KEYCLOAK_URL        = local.keycloak_url
    LAPI_KEYCLOAK_REALM      = local.keycloak_realm
    LAPI_KEYCLOAK_CLIENT_ID  = local.keycloak_client_id
    LAPI_KEYCLOAK_ADMIN_ROLE = var.keycloak_admin_role
    LAPI_PUBLIC_URL          = local.public_url
    }, local.keycloak_secret ? { LAPI_KEYCLOAK_CLIENT_SECRET_OCID = local.keycloak_secret_id } : {},
    # Keycloak alone decides second factors (its realm flow requires an authenticator for
    # administrators); Lapi does not re-check the AMR claim, which this realm leaves empty.
    var.keycloak_hosted ? { LAPI_KEYCLOAK_AUDITOR_ROLE = "lapi-auditor", LAPI_KEYCLOAK_CONTRIBUTOR_ROLE = "lapi-contributor", LAPI_KEYCLOAK_REQUIRE_ADMIN_MFA = "false" } : {},
  length(var.keycloak_identity_providers) > 0 ? { LAPI_KEYCLOAK_IDENTITY_PROVIDERS = join(",", [for alias, label in var.keycloak_identity_providers : "${alias}=${label}"]) } : {}) : {}

  registry  = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.lapi.namespace}"
  api_image = "${local.registry}/${var.name}/api:${var.image_tag}"
  web_image = "${local.registry}/${var.name}/web:${var.image_tag}"

  backend_env = {
    DATABASE_PROVIDER                     = "oracle"
    ORACLE_USER                           = "ADMIN"
    ORACLE_DSN                            = local.db_dsn
    ORACLE_PASSWORD_SECRET_OCID           = oci_vault_secret.db_password.id
    LAPI_MASTER_KEY_SECRET_OCID           = oci_vault_secret.master_key.id
    LAPI_VAULT_AUTH_MODE                  = "resource_principal"
    LAPI_FIRST_ADMIN_USERNAME             = var.admin_username
    LAPI_FIRST_ADMIN_PASSWORD_SECRET_OCID = oci_vault_secret.first_admin.id
    LAPI_CONTROL_STORE                    = "oci"
    LAPI_CONTROL_PREFIX                   = "${var.name}-control"
    SEARCH_PROVIDER                       = "oracle"
    STORAGE_PROVIDER                      = "oci"
    OCI_AUTH_MODE                         = "resource_principal"
    OCI_REGION                            = var.region
    OCI_NAMESPACE                         = data.oci_objectstorage_namespace.lapi.namespace
    OCI_BUCKET                            = oci_objectstorage_bucket.lapi.name
    OCI_OBJECT_PREFIX                     = "${var.name}-documents"
    LAPI_STORAGE_ROOT                     = "/data"
    HF_HOME                               = "/data/model-cache"
    MODEL_PROVIDER                        = "ollama"
    EMBEDDING_PROVIDER                    = "ollama"
    LAPI_MODEL                            = var.chat_model
    EMBEDDING_MODEL                       = var.embedding_model
    LAPI_OLLAMA_URL                       = "http://127.0.0.1:11434"
    LAPI_AGENT_ENGINE                     = "langgraph"
    LAPI_CHAT_MODE                        = "auto"
    LAPI_RERANKER                         = "local" # Model files are baked into the API image at /opt/lapi-reranker.
    LAPI_OCR_ENABLED                      = "true"  # Images and scanned pages use the dataset's cloud OCR model (OpenAI gpt-4o/gpt-4o-mini or Gemini); nothing runs locally.
    LANGSMITH_TRACING                     = "false"
    LAPI_ALLOW_MOCK                       = "false"
    COOKIE_SECURE                         = var.https ? "true" : "false"
    LAPI_OPENFGA_URL                      = "http://127.0.0.1:8080"
  }
}

resource "oci_container_instances_container_instance" "lapi" {
  count                    = var.image_tag == "" ? 0 : 1
  compartment_id           = var.compartment_ocid
  availability_domain      = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name             = "${var.name}-app"
  shape                    = var.container_shape
  container_restart_policy = "ALWAYS"

  shape_config {
    ocpus         = var.container_ocpus
    memory_in_gbs = var.container_memory_gbs
  }

  vnics {
    subnet_id             = oci_core_subnet.private.id
    is_public_ip_assigned = false
    display_name          = "${var.name}-app"
  }

  volumes {
    name          = "scratch"
    volume_type   = "EMPTYDIR"
    backing_store = "EPHEMERAL_STORAGE"
  }

  dynamic "volumes" {
    for_each = var.https ? [1] : []
    content {
      name        = "caddy-config"
      volume_type = "CONFIGFILE"
      configs {
        file_name = "Caddyfile"
        data      = base64encode(local.caddyfile)
      }
    }
  }

  dynamic "volumes" {
    for_each = var.keycloak_hosted ? [1] : []
    content {
      name        = "keycloak-import"
      volume_type = "CONFIGFILE"
      configs {
        file_name = "realm-lapi.json"
        data      = base64encode(local.keycloak_realm_json)
      }
    }
  }

  containers {
    display_name          = "api"
    image_url             = local.api_image
    environment_variables = merge(local.backend_env, local.keycloak_env, var.https ? { LAPI_TLS_STATE_DIR = "/data/caddy" } : {}, local.keycloak_bootstrap_env)
    volume_mounts {
      volume_name = "scratch"
      mount_path  = "/data"
    }
    health_checks {
      health_check_type        = "HTTP"
      port                     = 8000
      path                     = "/ready"
      initial_delay_in_seconds = 60
      interval_in_seconds      = 30
      failure_threshold        = 5
    }
  }

  containers {
    display_name          = "worker"
    image_url             = local.api_image
    command               = ["python", "-m", "lapi_app.worker"]
    environment_variables = merge(local.backend_env, local.keycloak_env)
    volume_mounts {
      volume_name = "scratch"
      mount_path  = "/data"
    }
  }

  # Local models, as on lapi-vm: no paid AI calls. The models are pulled into the
  # scratch volume when the instance starts (a few minutes on first start).
  containers {
    display_name = "ollama"
    image_url    = "docker.io/ollama/ollama:0.35.1"
    command      = ["/bin/sh", "-c", "ollama serve & until ollama list >/dev/null 2>&1; do sleep 2; done; ollama pull ${var.chat_model} && ollama pull ${var.embedding_model}; wait"]
    environment_variables = {
      OLLAMA_MODELS            = "/data/models"
      OLLAMA_NO_CLOUD          = "1"
      OLLAMA_NUM_PARALLEL      = "1"
      OLLAMA_MAX_LOADED_MODELS = "1"
      OLLAMA_CONTEXT_LENGTH    = "4096"
      OLLAMA_KEEP_ALIVE        = "30m"
    }
    volume_mounts {
      volume_name = "scratch"
      mount_path  = "/data"
      sub_path    = "ollama"
    }
  }

  # OpenFGA answers every permission check (authz.py). Its store is in memory and
  # the api rebuilds it from the database, so it needs no database of its own.
  # Only reachable on the instance's localhost; the playground is off (port 3000 is web's).
  containers {
    display_name = "openfga"
    image_url    = "docker.io/openfga/openfga:v1.22.0"
    arguments    = ["run"]
    environment_variables = {
      OPENFGA_DATASTORE_ENGINE   = "memory"
      OPENFGA_HTTP_ADDR          = "127.0.0.1:8080"
      OPENFGA_GRPC_ADDR          = "127.0.0.1:8081"
      OPENFGA_PLAYGROUND_ENABLED = "false"
      OPENFGA_METRICS_ENABLED    = "false"
      OPENFGA_LOG_FORMAT         = "json"
    }
  }

  containers {
    display_name = "web"
    image_url    = local.web_image
    environment_variables = {
      API_INTERNAL_URL       = "http://127.0.0.1:8000"
      LAPI_DEPLOYMENT_TARGET = "oci-container-instances"
      LAPI_API_LOCATION      = "oci"
      LAPI_WORKER_LOCATION   = "oci"
      LAPI_MODEL_LOCATION    = "cloud"
    }
  }

  # HTTPS: waits until the api has put back the saved certificate (tls_state.py), so a
  # deployment does not ask Let's Encrypt again (it allows five per week for one name).
  dynamic "containers" {
    for_each = var.https ? [1] : []
    content {
      display_name = "caddy"
      image_url    = "docker.io/library/caddy:2.10.2"
      command      = ["/bin/sh", "-c", "until [ -f /data/.lapi-restored ]; do sleep 2; done; exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"]
      environment_variables = {
        XDG_DATA_HOME   = "/data"
        XDG_CONFIG_HOME = "/tmp/caddy-config"
      }
      # The api's user (Dockerfile uid 10001): Caddy keeps its files owner-only, and the
      # api must read them to save the certificate. The image may bind 80/443 without root.
      security_context {
        security_context_type = "LINUX"
        run_as_user           = 10001
        run_as_group          = 10001
      }
      volume_mounts {
        volume_name = "scratch"
        mount_path  = "/data"
        sub_path    = "caddy"
      }
      volume_mounts {
        volume_name = "caddy-config"
        mount_path  = "/etc/caddy"
      }
    }
  }

  # Sign-in for Lapi (keycloak.tf). Waits until the api has created its database user and
  # handed it its secrets (keycloak_bootstrap.py); only Caddy reaches it, on localhost.
  dynamic "containers" {
    for_each = var.keycloak_hosted ? [1] : []
    content {
      display_name          = "keycloak"
      image_url             = local.keycloak_image
      command               = ["/bin/bash", "-c", "until [ -f /secrets/.ready ]; do sleep 2; done; export KC_DB_PASSWORD=\"$(< /secrets/db-password)\" KC_BOOTSTRAP_ADMIN_PASSWORD=\"$(< /secrets/admin-password)\" LAPI_CLIENT_SECRET=\"$(< /secrets/client-secret)\"; exec /opt/keycloak/bin/kc.sh start --optimized --import-realm"]
      environment_variables = local.keycloak_container_env
      resource_config {
        memory_limit_in_gbs = var.keycloak_memory_gbs
      }
      # Same user as the api, which owns the secret files (0600); group 0 as in Keycloak's image.
      security_context {
        security_context_type = "LINUX"
        run_as_user           = 10001
        run_as_group          = 0
      }
      volume_mounts {
        volume_name  = "scratch"
        mount_path   = "/secrets"
        sub_path     = "keycloak-secrets"
        is_read_only = true
      }
      volume_mounts {
        volume_name = "keycloak-import"
        mount_path  = "/opt/keycloak/data/import"
      }
    }
  }

  depends_on = [oci_identity_policy.containers]

  lifecycle {
    precondition {
      condition     = !var.keycloak_hosted || var.https
      error_message = "keycloak_hosted needs https = true: Caddy serves Keycloak at https://sso.<load balancer IP>.sslip.io."
    }
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_vnic" "lapi" {
  count   = length(oci_container_instances_container_instance.lapi)
  vnic_id = oci_container_instances_container_instance.lapi[0].vnics[0].vnic_id
}
