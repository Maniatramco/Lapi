# Public entry point with a stable IP: a 10 Mbps flexible load balancer (Always
# Free eligible) forwarding HTTP to the web container in the private subnet.
# For HTTPS, add a certificate and a port-443 listener here.

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

resource "oci_load_balancer_backend_set" "web" {
  load_balancer_id = oci_load_balancer_load_balancer.lapi.id
  name             = "web"
  policy           = "ROUND_ROBIN"
  health_checker {
    protocol    = "HTTP"
    port        = 3000
    url_path    = "/"
    return_code = 200
  }
}

resource "oci_load_balancer_backend" "web" {
  count            = length(oci_container_instances_container_instance.lapi)
  load_balancer_id = oci_load_balancer_load_balancer.lapi.id
  backendset_name  = oci_load_balancer_backend_set.web.name
  ip_address       = data.oci_core_vnic.lapi[0].private_ip_address
  port             = 3000
}

resource "oci_load_balancer_listener" "http" {
  load_balancer_id         = oci_load_balancer_load_balancer.lapi.id
  name                     = "http"
  default_backend_set_name = oci_load_balancer_backend_set.web.name
  port                     = 80
  protocol                 = "HTTP"
}
