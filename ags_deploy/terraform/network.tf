# One VCN: a public subnet for the container instance (web traffic only; there is
# no SSH because there is no VM) and a private subnet for the database's private
# endpoint, which is never reachable from the internet.

resource "oci_core_vcn" "lapi" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name}-vcn"
  dns_label      = var.name
}

resource "oci_core_internet_gateway" "lapi" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-igw"
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-public-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.lapi.id
  }
}

resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-public-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
  dynamic "ingress_security_rules" {
    for_each = [80, 443]
    content {
      description = "Web"
      source      = "0.0.0.0/0"
      protocol    = "6"
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
}

resource "oci_core_security_list" "private" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-private-sl"

  egress_security_rules {
    destination = var.vcn_cidr
    protocol    = "6"
  }
  ingress_security_rules {
    description = "Database TLS from inside the VCN"
    source      = var.vcn_cidr
    protocol    = "6"
    tcp_options {
      min = 1522
      max = 1522
    }
  }
}

resource "oci_core_subnet" "public" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.lapi.id
  cidr_block        = cidrsubnet(var.vcn_cidr, 8, 1)
  display_name      = "${var.name}-public"
  dns_label         = "pub"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]
}

resource "oci_core_subnet" "private" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.lapi.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 2)
  display_name               = "${var.name}-private"
  dns_label                  = "priv"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.private.id]
}
