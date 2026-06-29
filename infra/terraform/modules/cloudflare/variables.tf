variable "account_id" {
  description = "Cloudflare account ID that owns the Worker."
  type        = string
}

variable "zone_id" {
  description = "Cloudflare zone ID for the app domain."
  type        = string
}

variable "worker_name" {
  description = "Name of the Worker script (serves SPA static assets + edge JWT verify + proxy)."
  type        = string
  default     = "atlas-web"
}

variable "worker_script_content" {
  description = "Worker script source. Defaults to a minimal placeholder; real CI deploys the built bundle via Wrangler/OIDC and Terraform only manages the route + DNS. Override to let Terraform own the script."
  type        = string
  default     = null
}

variable "app_hostname" {
  description = "Fully-qualified hostname the app is served on, e.g. \"app.example.com\"."
  type        = string
}

variable "origin_api_url" {
  description = "Origin URL the Worker proxies API/SSE requests to (the EKS ingress / LB). Passed to the Worker as a plaintext binding."
  type        = string
}

variable "jwt_issuer" {
  description = "Expected JWT issuer the edge Worker validates (iss claim). Passed as a plaintext binding."
  type        = string
  default     = "atlas"
}

variable "jwt_audience" {
  description = "Expected JWT audience the edge Worker validates (aud claim)."
  type        = string
  default     = "atlas-api"
}

variable "create_dns_record" {
  description = "Create the proxied DNS record for app_hostname. Disable if DNS is managed elsewhere."
  type        = bool
  default     = true
}

variable "dns_record_type" {
  description = "DNS record type for the app hostname (CNAME for a Worker route on a hostname, A as a placeholder)."
  type        = string
  default     = "CNAME"
}

variable "dns_record_value" {
  description = "Target for the DNS record (e.g. the zone apex or a workers.dev hostname). Workers routes attach independently of the record target."
  type        = string
  default     = "100::" # documented Cloudflare blackhole target for proxied-only hostnames
}
