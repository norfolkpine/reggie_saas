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

variable "github_repo" {
  description = "GitHub repository in format 'owner/repo'"
  type        = string
  default     = "norfolkpine/reggie_saas"  # Update this to your actual repo
}
