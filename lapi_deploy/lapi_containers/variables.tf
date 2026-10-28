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

variable "admin_username" {
  description = "First administrator, created once at start-up. Its password is generated into Vault."
  type        = string
  default     = "admin"
}

variable "chat_model" {
  description = "Local Ollama chat model (as on lapi-vm)."
  type        = string
  default     = "qwen3:4b"
}

variable "embedding_model" {
  description = "Local Ollama embedding model (as on lapi-vm)."
  type        = string
  default     = "nomic-embed-text"
}

# --- Autonomous AI Database ------------------------------------------------

variable "existing_db_id" {
  description = "OCID of the existing Autonomous AI Database Lapi uses (lapidb)."
  type        = string
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

# --- Sign-in (Keycloak) and permissions (OpenFGA) ---

variable "keycloak_url" {
  description = "Your existing Keycloak, e.g. https://sso.example.com (no /realms/...). Empty keeps Lapi's own password sign-in."
  type        = string
  default     = ""
}

variable "keycloak_realm" {
  type    = string
  default = ""
}

variable "keycloak_client_id" {
  description = "OpenID Connect client for Lapi in that realm (standard flow, PKCE S256)."
  type        = string
  default     = "lapi"
}

variable "keycloak_confidential_client" {
  description = "true when the Keycloak client has Client authentication on: its secret goes in the Vault secret lapi-keycloak-client-secret."
  type        = bool
  default     = true
}

variable "keycloak_admin_role" {
  description = "Realm or client role that makes someone a Lapi administrator."
  type        = string
  default     = "lapi-administrator"
}

variable "public_url" {
  description = "Address people open Lapi at; Keycloak redirects back to <public_url>/api/auth/keycloak/callback. Empty uses https://<https_hostname> (or http://<load balancer IP> when https is off)."
  type        = string
  default     = ""
}

# --- HTTPS (Caddy in the container instance, certificate from Let's Encrypt) ---

variable "https" {
  description = "Serve Lapi over HTTPS: Caddy gets and renews a Let's Encrypt certificate; plain HTTP redirects to it."
  type        = bool
  default     = true
}

variable "https_hostname" {
  description = "Name the certificate is for. Empty uses lapi.<load balancer IP>.sslip.io, which needs no domain or DNS setup."
  type        = string
  default     = ""
}
