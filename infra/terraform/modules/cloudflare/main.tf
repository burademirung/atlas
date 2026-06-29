# ---------------------------------------------------------------------------
# Cloudflare: the single Worker that serves the SPA static assets and performs
# edge JWT verification + rate-limit + proxy to the EKS origin (§9/§10). The SSE
# route must stream (no buffering) — asserted by an acceptance test elsewhere.
#
# In practice the Worker bundle is built and deployed by CI (Wrangler over an
# OIDC/scoped token), and Terraform owns the route + DNS + non-secret bindings.
# Set worker_script_content to let Terraform own the script instead.
# ---------------------------------------------------------------------------

locals {
  # Minimal, syntactically valid placeholder so `terraform apply` produces a
  # routable Worker even before the real bundle is deployed by CI.
  placeholder_script = <<-EOT
    export default {
      async fetch(request, env) {
        return new Response("Atlas edge worker: bundle not yet deployed", {
          status: 503,
          headers: { "content-type": "text/plain" },
        });
      },
    };
  EOT

  script_content = coalesce(var.worker_script_content, local.placeholder_script)
}

resource "cloudflare_workers_script" "app" {
  account_id = var.account_id
  name       = var.worker_name
  content    = local.script_content
  module     = true

  # Non-secret runtime config. Secrets (e.g. the JWT public key / JWKS) are set
  # out-of-band via `wrangler secret put` or a secret_text_binding in CI, never
  # committed here.
  plain_text_binding {
    name = "ORIGIN_API_URL"
    text = var.origin_api_url
  }

  plain_text_binding {
    name = "JWT_ISSUER"
    text = var.jwt_issuer
  }

  plain_text_binding {
    name = "JWT_AUDIENCE"
    text = var.jwt_audience
  }
}

# Route all traffic for the app hostname through the Worker.
resource "cloudflare_workers_route" "app" {
  zone_id     = var.zone_id
  pattern     = "${var.app_hostname}/*"
  script_name = cloudflare_workers_script.app.name
}

# Proxied DNS record so the hostname resolves through Cloudflare's edge.
resource "cloudflare_record" "app" {
  count = var.create_dns_record ? 1 : 0

  zone_id = var.zone_id
  name    = var.app_hostname
  type    = var.dns_record_type
  content = var.dns_record_value
  proxied = true
  comment = "Atlas app hostname; traffic served by the ${var.worker_name} Worker"
}
