# HTTPS on OCI with Caddy and sslip.io (Lapi v26.1.16.14 to .16)

## Why
Many office networks, VPNs and browsers block plain `http://` to a bare IP. The fix is a real HTTPS name.
`sslip.io` maps `anything.<ip>.sslip.io` to `<ip>`, so Let's Encrypt can issue a certificate without a domain.

## Shape (OCI Container Instance behind a flexible load balancer)
- New container `caddy` (`docker.io/library/caddy:2.10.2`) in the same instance; config via a **CONFIGFILE**
  volume (`configs { file_name = "Caddyfile", data = base64encode(local.caddyfile) }`).
- Caddyfile:
  ```
  { admin off }
  app.<ip>.sslip.io { encode zstd gzip
                      reverse_proxy 127.0.0.1:3000 }
  http:// { redir https://app.<ip>.sslip.io{uri} permanent }
  ```
  Caddy still answers ACME HTTP-01 challenges on :80 before the catch-all redirect.
- Load balancer: listeners 80 and 443 as **TCP** pass-through to backend sets `caddy-http` (80) and
  `caddy-https` (443) with TCP health checks. Security lists: LB → instance on 80/443 (not 3000 any more).
- Variables: `https` (default true) and `https_hostname` (default `app.<lb ip>.sslip.io`); `public_url` defaults
  to the HTTPS address; `COOKIE_SECURE = var.https ? "true" : "false"`. Output `url`.
- Validate the Caddyfile locally: `docker run --rm -v <dir>:/etc/caddy:ro caddy:2.10.2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`.

## Keep the certificate across deploys (essential)
Every deploy replaces the instance and empties its scratch volume, and Let's Encrypt allows only
**5 certificates per week for the same name**. So:
1. The api module `tls_state.py` (env `LAPI_TLS_STATE_DIR=/data/caddy`, api only):
   - at startup, **before anything else**, restore `tls/caddy-data.tar.gz` from the control bucket into the folder
     (`tarfile.extractall(filter='data')`, size limit), then write marker `.lapi-restored` - even if the bucket is
     unreachable after a few retries, so Caddy still starts;
   - every 5 minutes, fingerprint the folder (skip locks and the marker) and upload when it changed.
   - The baseline for "changed" is **what was restored** (empty on first deploy), not the folder when the loop
     starts - otherwise a certificate obtained during startup is never saved (bug fixed in v26.1.16.15).
2. Caddy waits for the marker: `command = ["/bin/sh","-c","until [ -f /data/.lapi-restored ]; do sleep 2; done; exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile"]`,
   with the scratch volume `sub_path = "caddy"` mounted at `/data` and `XDG_DATA_HOME=/data`,
   `XDG_CONFIG_HOME=/tmp/caddy-config`.
3. **Run Caddy as the api's uid** (`security_context { security_context_type = "LINUX", run_as_user = 10001, run_as_group = 10001 }`).
   Caddy writes owner-only files; when it ran as root the api (uid 10001) could not read them and `rglob`
   silently returned nothing (bug fixed in v26.1.16.16). The official Caddy image may bind 80/443 as non-root.
   Log a warning for unreadable folders (`os.walk(onerror=...)`) instead of skipping silently.
4. Verify after deploy: list `<control-prefix>/tls/` in the bucket and the file names inside the archive
   (`certificates/.../<host>.crt`, `.key`, `.json`) - never print key contents. On the next deploy the
   certificate's `notBefore` must stay the same (`openssl s_client ... | openssl x509 -noout -dates`).

## Terraform pitfall
Switching the port-80 listener from the old `web` backend set to `caddy-http` in one apply failed with
**409 "Backend Set 'web' is configured in Listener 'http'"** because Terraform deleted the old set first, after
the instance was already destroyed (site down). Recovery: `terraform apply '-target=oci_load_balancer_listener.http'`
(creates the new sets and moves the listener), then plan/apply the rest. Next time do it in two applies up front.

## Aegis note
Aegis already runs Caddy on OKE with a persistent volume at `https://aegis.92.4.67.183.sslip.io`, so its
certificates survive deploys; only reuse the headers/proxy-protocol parts there.
