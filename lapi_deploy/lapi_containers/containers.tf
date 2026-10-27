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
  keycloak        = var.keycloak_url != ""
  keycloak_secret = local.keycloak && var.keycloak_confidential_client
  public_url      = trimsuffix(var.public_url != "" ? var.public_url : "http://${oci_load_balancer_load_balancer.lapi.ip_address_details[0].ip_address}", "/")
  # Sign-in through Keycloak (keycloak_auth.py); empty keeps Lapi's password sign-in.
  keycloak_env = local.keycloak ? merge({
    LAPI_KEYCLOAK_URL        = var.keycloak_url
    LAPI_KEYCLOAK_REALM      = var.keycloak_realm
    LAPI_KEYCLOAK_CLIENT_ID  = var.keycloak_client_id
    LAPI_KEYCLOAK_ADMIN_ROLE = var.keycloak_admin_role
    LAPI_PUBLIC_URL          = local.public_url
  }, local.keycloak_secret ? { LAPI_KEYCLOAK_CLIENT_SECRET_OCID = oci_vault_secret.keycloak_client[0].id } : {}) : {}

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
    LAPI_OCR_ENABLED                      = "false"
    LANGSMITH_TRACING                     = "false"
    LAPI_ALLOW_MOCK                       = "false"
    COOKIE_SECURE                         = "false" # Set "true" once the load balancer serves HTTPS.
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

  containers {
    display_name          = "api"
    image_url             = local.api_image
    environment_variables = merge(local.backend_env, local.keycloak_env)
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

  depends_on = [oci_identity_policy.containers]
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_vnic" "lapi" {
  count   = length(oci_container_instances_container_instance.lapi)
  vnic_id = oci_container_instances_container_instance.lapi[0].vnics[0].vnic_id
}
