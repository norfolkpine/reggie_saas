# Production environment variables
project_id     = "bh-opie"
region         = "australia-southeast1"
zone           = "australia-southeast1-a"
environment    = "production"
project_name   = "bh-opie"

# VM Configuration
vm_machine_type = "e2-medium"
vm_disk_size    = 30

# Database Configuration
db_tier      = "db-f1-micro"
db_disk_size = 10
db_disk_type = "PD_SSD"

# Common labels applied to all resources
common_labels = {
  environment = "production"
  project     = "bh-opie"
  managed_by  = "terraform"
  team        = "compliance"
}
