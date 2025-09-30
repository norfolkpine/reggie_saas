output "vm_private_ip" {
  description = "Private IP address of the VM"
  value       = google_compute_instance.opie_stack_vm.network_interface[0].network_ip
}

output "db_connection_name" {
  description = "CloudSQL connection name"
  value       = google_sql_database_instance.db0.connection_name
}

output "db_private_ip" {
  description = "CloudSQL private IP address"
  value       = google_sql_database_instance.db0.private_ip_address
}

output "ssh_command" {
  description = "SSH command to connect via IAP"
  value       = "gcloud compute ssh opie-stack-vm --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap"
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

output "media_bucket_name" {
  description = "Media storage bucket name"
  value       = google_storage_bucket.media_bucket.name
}

output "static_bucket_name" {
  description = "Static files storage bucket name"
  value       = google_storage_bucket.static_bucket.name
}

output "docs_bucket_name" {
  description = "Documents storage bucket name"
  value       = google_storage_bucket.docs_bucket.name
}

output "access_logs_bucket_name" {
  description = "Access logs bucket name"
  value       = google_storage_bucket.access_logs_bucket.name
}

output "kms_key_ring_name" {
  description = "KMS key ring name for storage encryption"
  value       = google_kms_key_ring.storage_key_ring.name
}

output "kms_crypto_key_name" {
  description = "KMS crypto key name for storage encryption"
  value       = google_kms_crypto_key.storage_key.name
}
