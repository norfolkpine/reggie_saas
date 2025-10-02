# Production environment variables
project_id     = "bh-opie"
region         = "australia-southeast1"
zone           = "australia-southeast1-a"
environment    = "production"
project_name   = "bh-opie"

# VM Configuration
vm_machine_type = "e2-medium"
vm_disk_size    = 30
vm_image_family = "debian-12"
vm_image_project = "debian-cloud"

# Database Configuration
db_tier      = "db-f1-micro"
db_disk_size = 10
db_disk_type = "PD_SSD"

# Cloud Run Service Configuration
gcs_prefix = "opie-data/global/library/"
pgvector_schema = "ai"
pgvector_table = "kb__vector_table"
vault_pgvector_table = "vault_vector_table"
django_api_url = "https://api.opie.sh"
local_development = false

# Common labels applied to all resources
common_labels = {
  environment = "production"
  project     = "bh-opie"
  managed_by  = "terraform"
  team        = "compliance"
}
