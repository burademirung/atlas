output "worker_name" {
  description = "Name of the deployed Worker script."
  value       = cloudflare_workers_script.app.name
}

output "worker_route_pattern" {
  description = "Route pattern bound to the Worker."
  value       = cloudflare_workers_route.app.pattern
}

output "app_hostname" {
  description = "Hostname the app is served on."
  value       = var.app_hostname
}

output "dns_record_id" {
  description = "ID of the managed DNS record (null when create_dns_record is false)."
  value       = var.create_dns_record ? cloudflare_record.app[0].id : null
}
