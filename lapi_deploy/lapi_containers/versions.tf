terraform {
  required_version = ">= 1.6"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 7.0, < 8.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6, < 4.0"
    }
  }
}

# Authenticates with ~/.oci/config (profile below) like the OCI CLI.
provider "oci" {
  region              = var.region
  config_file_profile = var.oci_profile
}
