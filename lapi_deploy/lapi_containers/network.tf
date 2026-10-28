# Public subnet: only the load balancer (ports 80/443 in; no SSH, there is no VM).
# Private subnet: the container instance. It reaches the internet (model APIs,
# image pulls) through the NAT gateway and OCI services, including the Autonomous
# Database endpoint, through the service gateway, so the database sees it as
# this VCN and its access list can name the VCN.

data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

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

resource "oci_core_nat_gateway" "lapi" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-nat"
}

resource "oci_core_service_gateway" "lapi" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-sgw"
  services {
    service_id = data.oci_core_services.all.services[0].id
  }
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

resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-private-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_nat_gateway.lapi.id
  }
  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.lapi.id
  }
}

resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.lapi.id
  display_name   = "${var.name}-public-sl"

  dynamic "egress_security_rules" {
    for_each = toset(values(local.lb_ports))
    content {
      description = "Load balancer to the container instance (Caddy, or web when https is off)"
      destination = local.private_cidr
      protocol    = "6"
      tcp_options {
        min = egress_security_rules.value
        max = egress_security_rules.value
      }
    }
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
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
  dynamic "ingress_security_rules" {
    for_each = toset(values(local.lb_ports))
    content {
      description = "Caddy (or web when https is off), from the load balancer only"
      source      = local.public_cidr
      protocol    = "6"
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
}

locals {
  public_cidr  = cidrsubnet(var.vcn_cidr, 8, 1)
  private_cidr = cidrsubnet(var.vcn_cidr, 8, 2)
}

resource "oci_core_subnet" "public" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.lapi.id
  cidr_block        = local.public_cidr
  display_name      = "${var.name}-public"
  dns_label         = "pub"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]
}

resource "oci_core_subnet" "private" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.lapi.id
  cidr_block                 = local.private_cidr
  display_name               = "${var.name}-private"
  dns_label                  = "priv"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private.id
  security_list_ids          = [oci_core_security_list.private.id]
}
