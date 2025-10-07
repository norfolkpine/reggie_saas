output "vm_external_ip" {
  description = "Static external IP address of the VM"
  value       = google_compute_address.vm_external_ip.address
}

output "db_connection_name" {
  description = "CloudSQL connection name"
  value       = google_sql_database_instance.db0.connection_name
}

output "db_public_ip" {
  description = "CloudSQL public IP address"
  value       = google_sql_database_instance.db0.public_ip_address
}

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP Region"
  value       = var.region
}

output "zone" {
  description = "GCP Zone"
  value       = var.zone
}
