# Uploaded documents, revisions and result files.

data "oci_objectstorage_namespace" "lapi" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "lapi" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.lapi.namespace
  name           = "${var.name}-documents"
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
}
