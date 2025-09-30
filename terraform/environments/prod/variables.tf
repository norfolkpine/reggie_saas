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

variable "admin_email" {
  description = "Admin email for IAP access"
  type        = string
}

variable "media_bucket_name" {
  description = "Name of the media storage bucket"
  type        = string
  default     = "bh-opie-media"
}

variable "static_bucket_name" {
  description = "Name of the static files storage bucket"
  type        = string
  default     = "bh-opie-static"
}

variable "docs_bucket_name" {
  description = "Name of the documents storage bucket"
  type        = string
  default     = "bh-opie-docs"
}
