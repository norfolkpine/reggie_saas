variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "bh-opie"
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "australia-southeast1"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "australia-southeast1-a"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "bh-opie"
}

variable "vm_machine_type" {
  description = "Machine type for the VM instance"
  type        = string
  default     = "e2-medium"
}

variable "vm_disk_size" {
  description = "Boot disk size for the VM instance"
  type        = number
  default     = 30
}

variable "vm_image_family" {
  description = "Image family for the VM instance"
  type        = string
  default     = "debian-12"
}

variable "vm_image_project" {
  description = "Image project for the VM instance"
  type        = string
  default     = "debian-cloud"
}

variable "db_tier" {
  description = "CloudSQL instance tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_disk_size" {
  description = "CloudSQL disk size"
  type        = number
  default     = 10
}

variable "db_disk_type" {
  description = "CloudSQL disk type"
  type        = string
  default     = "PD_SSD"
}

variable "common_labels" {
  description = "Common labels to apply to all resources"
  type        = map(string)
  default = {
    environment = "production"
    project     = "bh-opie"
    managed_by  = "terraform"
    team        = "compliance"
  }
}

# Cloud Run Service Configuration
variable "gcs_prefix" {
  description = "GCS prefix for file storage"
  type        = string
  default     = "opie-data/global/library/"
}

variable "pgvector_schema" {
  description = "PostgreSQL schema for vector tables"
  type        = string
  default     = "ai"
}

variable "pgvector_table" {
  description = "Main vector table name"
  type        = string
  default     = "kb__vector_table"
}

variable "vault_pgvector_table" {
  description = "Vault vector table name"
  type        = string
  default     = "vault_vector_table"
}

variable "django_api_url" {
  description = "Django API URL"
  type        = string
  default     = "https://api.opie.sh"
}

variable "local_development" {
  description = "Whether running in local development mode"
  type        = bool
  default     = false
}
