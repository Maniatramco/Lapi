# Oracle Autonomous AI Database: Lapi's relational data and its vector index
# (native VECTOR columns and VECTOR_DISTANCE), replacing Postgres and Qdrant.
#
# Lapi uses an existing Always Free database (lapidb). Terraform only reads it.
# Always Free databases have no private endpoint: the containers reach its public
# endpoint through the VCN's service gateway, and the database's access list must
# include this VCN (see README). TLS, no wallet.

data "oci_database_autonomous_database" "lapi" {
  autonomous_database_id = var.existing_db_id
}

locals {
  # TLS (server-authenticated) connect descriptor for the LOW service.
  db_dsn = one([
    for p in data.oci_database_autonomous_database.lapi.connection_strings[0].profiles : p.value
    if p.consumer_group == "LOW" && p.tls_authentication == "SERVER" && p.host_format == "FQDN" && p.syntax_format == "LONG"
  ])
}
