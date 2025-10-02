terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
  
  backend "gcs" {
    bucket = "bh-opie-terraform-state"
    prefix = "envs/prod"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required Google Cloud APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "run.googleapis.com",
    "servicenetworking.googleapis.com",
    "containerregistry.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
  
  service = each.key
  disable_on_destroy = false
  
  timeouts {
    create = "10m"
    update = "10m"
  }
}

# VPC Network for better isolation
resource "google_compute_network" "main" {
  name                    = "${var.project_name}-vpc"
  auto_create_subnetworks = false
  mtu                     = 1460
  
  depends_on = [google_project_service.required_apis]
  
  timeouts {
    create = "5m"
    delete = "5m"
  }
}

# Subnet for our resources
resource "google_compute_subnetwork" "main" {
  name          = "${var.project_name}-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.main.id
  
  private_ip_google_access = true
  
  timeouts {
    create = "5m"
    delete = "5m"
  }
}

# Private IP range for Cloud SQL
resource "google_compute_global_address" "db_private_ip" {
  name          = "${var.project_name}-db-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
  
  depends_on = [google_project_service.required_apis]
}

# Service networking connection for private Cloud SQL
resource "google_service_networking_connection" "db_private_vpc_connection" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.db_private_ip.name]
  
  depends_on = [google_project_service.required_apis]
}

# CloudSQL Instance with private IP
resource "google_sql_database_instance" "db0" {
  name             = "db0"
  database_version = "POSTGRES_15"
  region           = var.region
  
  depends_on = [
    google_project_service.required_apis,
    google_service_networking_connection.db_private_vpc_connection
  ]

  settings {
    tier = var.db_tier
    
    disk_size = var.db_disk_size
    disk_type = var.db_disk_type
    
    location_preference {
      zone = var.zone
    }
    
    # Use private IP only for better security
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }
    
    # SSL is enabled by default on Cloud SQL instances
    
    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      location                       = var.region
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
    }
    
    maintenance_window {
      day          = 7
      hour         = 3
      update_track = "stable"
    }
    
    user_labels = merge(var.common_labels, {
      name = "db0"
      type = "cloudsql-instance"
    })
  }

  deletion_protection = false
  
  timeouts {
    create = "30m"
    update = "45m"
    delete = "30m"
  }
}

# Databases
# Note: 'postgres' database is created automatically with the instance

resource "google_sql_database" "bh_opie" {
  name     = "bh_opie"
  instance = google_sql_database_instance.db0.name
}

resource "google_sql_database" "bh_opie_test" {
  name     = "bh_opie_test"
  instance = google_sql_database_instance.db0.name
}

# Database initialization script
resource "google_storage_bucket_object" "db_init_script" {
  name   = "init-db.sql"
  bucket = google_storage_bucket.static.name
  content = <<-EOT
    -- Enable pgvector extension
    CREATE EXTENSION IF NOT EXISTS pgvector;
    
    -- Add any other database initialization here
  EOT
}

# Service account for VM
resource "google_service_account" "vm_service_account" {
  account_id   = "${var.project_name}-vm-sa"
  display_name = "VM Service Account"
  description  = "Service account for the application VM"
  
  depends_on = [google_project_service.required_apis]
}

# VM Instance with VPC and private database access
resource "google_compute_instance" "opie_stack_vm" {
  name         = "opie-stack-vm"
  machine_type = var.vm_machine_type
  zone         = var.zone
  
  depends_on = [google_project_service.required_apis]

  boot_disk {
    initialize_params {
      image = "${var.vm_image_project}/${var.vm_image_family}"
      size  = var.vm_disk_size
      type  = "pd-ssd"  # Use SSD for better performance
    }
  }

  labels = merge(var.common_labels, {
    name = "opie-stack-vm"
    type = "compute-instance"
  })

  # Use VPC network instead of default
  network_interface {
    network    = google_compute_network.main.id
    subnetwork = google_compute_subnetwork.main.id
    
    # Keep external IP for now (can be removed later for better security)
    access_config {
      // Ephemeral public IP
    }
  }

  # Service account for the VM
  service_account {
    email  = google_service_account.vm_service_account.email
    scopes = ["cloud-platform"]
  }

  tags = ["http-server", "https-server", "ssh-server", "app-server"]

  # SSH keys for GitHub Actions deployment
  metadata = {
    ssh-keys = "debian:ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQChAYqPXVPTpkMgCcGgAE4NYwNso+M81gavpOSzSc6SmEkoggvpFTT+W8osBUxcxBhYfqepVFa/4RlnxA/VZtxiqmFDGJ1DtoBHT9IwDVfgjCg87vDP1gQXOwZOme5amz2PQOGb1mXBBpfidTob0e4FEdU5htpLmcoodyJlbZXqs98qsbMLSuvRORI/l/igTkAsvH1xDgv7BeTdAjtvWfCPPyUZZh+1Cvjen8+7TaSmQFnfxEcHxLjYMvD5DjJACLItWwc5vJZlhpRKMigh/ThEFqlAfWtJOipJ0+fDdHmgc0pDtSjSOV3M0/76vSniOcdpDj3q0VDivEVTsYXLOVHln5nrpy0iDBeHcMt1dewF/lRhIecTS1IK6c3uElelo/CVqaRCn4lXTwKpJBBR1ZYEZwkWZrjjncwYFuuZccS3xSfQDglo4Tr2kne5t3DaHRkJHjlWA3tyz8sZ4jrbUMFSn16Nn/wb2T7d7FUgt51LJmrh9td+y3Ei9jdHFJWW1ExG0tDnRzEulvAevGdIvzIKjtjwS8W8YOJhMZL2vjFOFWrwM6mtn+5Os93ZaG/YLVF4rcmQx5QA06LiukKGeoI2JJAYYGdeg9zZCOMXCHVAWtVRVjZR/HNCsBBj7v/1jOaMxTJ3KDAltU+1n0827E+7IZcBE53R+KA/LL7XejlbQQ== github-actions-deploy"
  }

  # Startup script to install Docker and Docker Compose
  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -euo pipefail
    
    # Update system
    apt-get update
    apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
    
    # Add Docker's official GPG key
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    
    # Add Docker repository
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io
    
    # Install Docker Compose
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Add user to docker group
    usermod -aG docker $USER
    
    # Enable Docker service
    systemctl enable docker
    systemctl start docker
    
    # Create github-actions user and directories for deployment
    useradd -m -s /bin/bash github-actions || echo "User github-actions already exists"
    mkdir -p /home/github-actions/.gcp/creds
    chown -R github-actions:github-actions /home/github-actions
    chmod 755 /home/github-actions
    chmod 700 /home/github-actions/.gcp
    chmod 755 /home/github-actions/.gcp/creds
    
    # Add github-actions user to docker group
    usermod -aG docker github-actions
    
    # Add github-actions user to sudo group for deployment commands
    usermod -aG sudo github-actions
    
    # Create a marker file to indicate setup is complete
    touch /var/log/docker-setup-complete
    echo "Docker and Docker Compose installation completed at $(date)" >> /var/log/docker-setup-complete
  EOF
}

# Firewall Rules
resource "google_compute_firewall" "default_allow_ssh" {
  name    = "default-allow-ssh"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ssh-server"]
}

# Firewall rule for Cloud Identity-Aware Proxy (IAP)
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "allow-iap-ssh"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["ssh-server"]
}

resource "google_compute_firewall" "default_allow_internal" {
  name    = "default-allow-internal"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.0.0.0/24"]  # Updated to match our subnet range
}

resource "google_compute_firewall" "allow_http" {
  name    = "allow-http"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["http-server"]
}

resource "google_compute_firewall" "allow_https" {
  name    = "allow-https"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["https-server"]
}

# Secrets
resource "google_secret_manager_secret" "bh_opie_frontend" {
  secret_id = "bh-opie-frontend"
  
  depends_on = [google_project_service.required_apis]
  
  replication {
    auto {}
  }

  labels = merge(var.common_labels, {
    name = "bh-opie-frontend"
    type = "secret"
  })
}

resource "google_secret_manager_secret" "bh_opie_backend" {
  secret_id = "bh-opie-backend"
  
  depends_on = [google_project_service.required_apis]
  
  replication {
    auto {}
  }

  labels = merge(var.common_labels, {
    name = "bh-opie-backend"
    type = "secret"
  })
}

resource "google_secret_manager_secret" "bh_y_provider" {
  secret_id = "bh-y-provider"
  
  depends_on = [google_project_service.required_apis]
  
  replication {
    auto {}
  }

  labels = merge(var.common_labels, {
    name = "bh-y-provider"
    type = "secret"
  })
}

resource "google_secret_manager_secret" "llamaindex_ingester_env" {
  secret_id = "llamaindex-ingester-env"
  
  depends_on = [google_project_service.required_apis]
  
  replication {
    auto {}
  }

  labels = merge(var.common_labels, {
    name = "llamaindex-ingester-env"
    type = "secret"
  })
}

resource "google_secret_manager_secret" "nango_github_actions" {
  secret_id = "nango-github-actions"
  
  depends_on = [google_project_service.required_apis]
  
  replication {
    auto {}
  }

  labels = merge(var.common_labels, {
    name = "nango-github-actions"
    type = "secret"
  })
}

# Service Accounts
resource "google_service_account" "bh_opie_github_action" {
  account_id   = "bh-opie-github-action"
  display_name = "bh-opie-github-action"
  
  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "sql_backup" {
  account_id   = "sql-backup"
  display_name = "Cloud SQL Backup"
  
  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "bh_opie_storage" {
  account_id   = "bh-opie-storage"
  display_name = "Opie AI Cloud Storage Service Account"
  
  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "cloud_storage_backup" {
  account_id   = "cloud-storage-backup"
  display_name = "Cloud Storage Backup Service Account"
  
  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "github_actions" {
  account_id   = "github-actions"
  display_name = "GitHub Actions Service Account"
  
  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "cloud_run" {
  account_id   = "cloud-run"
  display_name = "Cloud Run Service Account"
  
  depends_on = [google_project_service.required_apis]
}



# Storage buckets
resource "google_storage_bucket" "static" {
  name          = "bh-opie-static"
  location      = var.region
  force_destroy = false
  uniform_bucket_level_access = true

  labels = merge(var.common_labels, {
    name = "bh-opie-static"
    type = "storage-bucket"
  })
}


resource "google_storage_bucket" "media" {
  name          = "bh-opie-media"
  location      = var.region
  force_destroy = false
  uniform_bucket_level_access = true

  labels = merge(var.common_labels, {
    name = "bh-opie-media"
    type = "storage-bucket"
  })
}

resource "google_storage_bucket" "docs" {
  name          = "bh-opie-docs"
  location      = var.region
  force_destroy = false
  uniform_bucket_level_access = true

  labels = merge(var.common_labels, {
    name = "bh-opie-docs"
    type = "storage-bucket"
  })
}

# Artifact Registry repository for container images
resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = "containers"
  description   = "App containers"
  format        = "DOCKER"

  labels = merge(var.common_labels, {
    name = "containers"
    type = "artifact-registry"
  })

  depends_on = [google_project_service.required_apis]
}


# IAM roles for Cloud Run service account
resource "google_project_iam_member" "cloud_run_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "cloud_run_storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "cloud_run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "cloud_run_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# IAM roles for GitHub Actions service account
resource "google_project_iam_member" "github_actions_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_storage_object_creator" {
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_artifact_registry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_container_registry_service_agent" {
  project = var.project_id
  role    = "roles/containerregistry.ServiceAgent"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Add specific createOnPush permission for GitHub Actions
resource "google_project_iam_member" "github_actions_create_on_push" {
  project = var.project_id
  role    = "roles/artifactregistry.repoAdmin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}


resource "google_project_iam_member" "github_actions_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_iam_service_account_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}


# Outputs for deployment scripts
output "deployment_vars" {
  description = "Deployment variables for scripts"
  value = {
    PROJECT_ID = var.project_id
    REGION = var.region
    ZONE = var.zone
    VM_NAME = "opie-stack-vm"
    MACHINE_TYPE = var.vm_machine_type
    IMAGE_FAMILY = var.vm_image_family
    IMAGE_PROJECT = var.vm_image_project
    INSTANCE_NAME = "db0"
    DB_NAME = "bh_opie"
    PG_VERSION = "POSTGRES_15"
    TIER = var.db_tier
    STORAGE = var.db_disk_size
    STATIC_BUCKET = "bh-opie-static"
    MEDIA_BUCKET = "bh-opie-media"
    DOCS_BUCKET = "bh-opie-docs"
    SERVICE_NAME = "llamaindex-ingestion"
    SECRET_NAME = "llamaindex-ingester-env"
    GCS_PREFIX = var.gcs_prefix
    PGVECTOR_SCHEMA = var.pgvector_schema
    PGVECTOR_TABLE = var.pgvector_table
    VAULT_PGVECTOR_TABLE = var.vault_pgvector_table
    DJANGO_API_URL = var.django_api_url
    LOCAL_DEVELOPMENT = var.local_development
    ARTIFACT_REGISTRY_REPO = google_artifact_registry_repository.containers.name
    ARTIFACT_REGISTRY_URL = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
  }
}
