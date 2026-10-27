variable "tenancy_ocid" {
  description = "Tenancy OCID (the dynamic group is created at tenancy level)."
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment for every Lapi resource."
  type        = string
}

variable "region" {
  type    = string
  default = "ap-mumbai-1"
}

variable "oci_profile" {
  description = "Profile in ~/.oci/config used by Terraform."
  type        = string
  default     = "DEFAULT"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "lapi"
}

variable "vcn_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

# --- Containers ----------------------------------------------------------------

variable "image_tag" {
  description = "Tag of the lapi/api and lapi/web images in OCIR. Leave empty on the first apply, push images, then set it."
  type        = string
  default     = ""
}

variable "container_shape" {
  description = "x86 shape, matching images built on a Windows/x86 computer."
  type        = string
  default     = "CI.Standard.E4.Flex"
}

variable "container_ocpus" {
  type    = number
  default = 2
}

variable "container_memory_gbs" {
  type    = number
  default = 16
}

variable "site_address" {
  description = "Domain name pointing at the container instance for automatic HTTPS, or ':80' for plain HTTP."
  type        = string
  default     = ":80"
}

variable "admin_username" {
  description = "First administrator, created once at start-up. Its password is generated into Vault."
  type        = string
  default     = "admin"
}

variable "model_provider" {
  type    = string
  default = "openai"
}

variable "embedding_provider" {
  type    = string
  default = "openai"
}

# --- Autonomous AI Database ------------------------------------------------

variable "db_name" {
  description = "Database name: letters and digits only, up to 30 characters."
  type        = string
  default     = "lapidb"
}

variable "db_version" {
  description = "Oracle AI Database version with native vector search."
  type        = string
  default     = "26ai"
}

variable "db_ecpu_count" {
  type    = number
  default = 2
}

variable "db_storage_gbs" {
  type    = number
  default = 20
}

# --- Vault -------------------------------------------------------------------

variable "existing_vault_id" {
  description = "Reuse this Vault (e.g. lapi-vault). Empty creates a new one."
  type        = string
  default     = ""
}

variable "existing_key_id" {
  description = "Encryption key in the existing Vault. Required with existing_vault_id."
  type        = string
  default     = ""
}
