# Public entry point with a stable IP: a 10 Mbps flexible load balancer (Always
# Free eligible). With https on (the default) it passes ports 80 and 443 straight
# through (TCP) to Caddy in the container instance, which holds the certificate.
# With https off it forwards HTTP to the web container.

resource "oci_load_balancer_load_balancer" "lapi" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.name}-lb"
  shape          = "flexible"
  subnet_ids     = [oci_core_subnet.public.id]
  is_private     = false
  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }
}

locals {
  # Backend set => container port. "web" keeps its name so turning https off restores it.
  lb_ports = var.https ? { caddy-http = 80, caddy-https = 443 } : { web = 3000 }
}

resource "oci_load_balancer_backend_set" "app" {
  for_each         = local.lb_ports
  load_balancer_id = oci_load_balancer_load_balancer.lapi.id
  name             = each.key
  policy           = "ROUND_ROBIN"
  health_checker {
    protocol    = var.https ? "TCP" : "HTTP"
    port        = each.value
    url_path    = var.https ? null : "/"
    return_code = var.https ? null : 200
  }
}

resource "oci_load_balancer_backend" "app" {
  for_each         = length(oci_container_instances_container_instance.lapi) > 0 ? local.lb_ports : {}
  load_balancer_id = oci_load_balancer_load_balancer.lapi.id
  backendset_name  = oci_load_balancer_backend_set.app[each.key].name
  ip_address       = data.oci_core_vnic.lapi[0].private_ip_address
  port             = each.value
}

resource "oci_load_balancer_listener" "http" {
  load_balancer_id         = oci_load_balancer_load_balancer.lapi.id
  name                     = "http"
  default_backend_set_name = oci_load_balancer_backend_set.app[var.https ? "caddy-http" : "web"].name
  port                     = 80
  protocol                 = var.https ? "TCP" : "HTTP"
}

resource "oci_load_balancer_listener" "https" {
  count                    = var.https ? 1 : 0
  load_balancer_id         = oci_load_balancer_load_balancer.lapi.id
  name                     = "https"
  default_backend_set_name = oci_load_balancer_backend_set.app["caddy-https"].name
  port                     = 443
  protocol                 = "TCP"
}
