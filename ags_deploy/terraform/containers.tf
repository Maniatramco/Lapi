# Lapi on OCI Container Instances: no VM. One container instance in the private
# subnet runs web, api and worker behind the load balancer (loadbalancer.tf).
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
  registry  = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.lapi.namespace}"
  api_image = "${local.registry}/${var.name}/api:${var.image_tag}"
  web_image = "${local.registry}/${var.name}/web:${var.image_tag}"

  backend_env = {
    DATABASE_PROVIDER                      = "oracle"
    ORACLE_USER                            = "ADMIN"
    ORACLE_DSN                             = local.db_dsn
    ORACLE_PASSWORD_SECRET_OCID            = oci_vault_secret.db_password.id
    AEGIS_MASTER_KEY_SECRET_OCID           = oci_vault_secret.master_key.id
    AEGIS_VAULT_AUTH_MODE                  = "resource_principal"
    AEGIS_FIRST_ADMIN_USERNAME             = var.admin_username
    AEGIS_FIRST_ADMIN_PASSWORD_SECRET_OCID = oci_vault_secret.first_admin.id
    AEGIS_CONTROL_STORE                    = "oci"
    AEGIS_CONTROL_PREFIX                   = "${var.name}-control"
    SEARCH_PROVIDER                        = "oracle"
    STORAGE_PROVIDER                       = "oci"
    OCI_AUTH_MODE                          = "resource_principal"
    OCI_REGION                             = var.region
    OCI_NAMESPACE                          = data.oci_objectstorage_namespace.lapi.namespace
    OCI_BUCKET                             = oci_objectstorage_bucket.lapi.name
    OCI_OBJECT_PREFIX                      = "${var.name}-documents"
    AEGIS_STORAGE_ROOT                     = "/data"
    HF_HOME                                = "/data/model-cache"
    MODEL_PROVIDER                         = var.model_provider
    EMBEDDING_PROVIDER                     = var.embedding_provider
    AEGIS_ALLOW_MOCK                       = "false"
    COOKIE_SECURE                          = "false" # Set "true" once the load balancer serves HTTPS.
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
    environment_variables = local.backend_env
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
    command               = ["python", "-m", "ags_app.worker"]
    environment_variables = local.backend_env
    volume_mounts {
      volume_name = "scratch"
      mount_path  = "/data"
    }
  }

  containers {
    display_name = "web"
    image_url    = local.web_image
    environment_variables = {
      API_INTERNAL_URL        = "http://127.0.0.1:8000"
      AEGIS_DEPLOYMENT_TARGET = "oci-container-instances"
      AEGIS_API_LOCATION      = "oci"
      AEGIS_WORKER_LOCATION   = "oci"
      AEGIS_MODEL_LOCATION    = "cloud"
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
