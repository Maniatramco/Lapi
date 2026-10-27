# Oracle Autonomous AI Database: Lapi's relational data and its vector index
# (native VECTOR columns and VECTOR_DISTANCE), replacing Postgres and Qdrant.
# Private endpoint in the private subnet, reachable only from inside the VCN,
# with TLS and no wallet.

resource "oci_database_autonomous_database" "lapi" {
  compartment_id              = var.compartment_ocid
  db_name                     = var.db_name
  display_name                = "${var.name}-db"
  db_version                  = var.db_version
  db_workload                 = "OLTP"
  compute_model               = "ECPU"
  compute_count               = var.db_ecpu_count
  data_storage_size_in_gb     = var.db_storage_gbs
  license_model               = "LICENSE_INCLUDED"
  admin_password              = random_password.db_admin.result
  is_mtls_connection_required = false
  subnet_id                   = oci_core_subnet.private.id
  private_endpoint_label      = "${var.name}db"
}

locals {
  # TLS (server-authenticated) connect descriptor for the LOW service.
  db_dsn = one([
    for p in oci_database_autonomous_database.lapi.connection_strings[0].profiles : p.value
    if p.consumer_group == "LOW" && p.tls_authentication == "SERVER" && p.host_format == "FQDN" && p.syntax_format == "LONG"
  ])
}
