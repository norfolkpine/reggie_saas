terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required Google Cloud APIs
resource "google_project_service" "compute_engine_api" {
  service = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_sql_api" {
  service = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secret_manager_api" {
  service = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam_api" {
  service = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_resource_manager_api" {
  service = "cloudresourcemanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "service_usage_api" {
  service = "serviceusage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iap_api" {
  service = "iap.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_resource_manager_api_v2" {
  service = "cloudresourcemanager.googleapis.com"
  disable_on_destroy = false
}

# VPC Network for private resources
resource "google_compute_network" "vpc_network" {
  name                    = "production-vpc"
  auto_create_subnetworks = false
  
  depends_on = [google_project_service.compute_engine_api]
}

resource "google_compute_subnetwork" "private_subnet" {
  name          = "private-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id
}

# CloudSQL Instance with private IP only
resource "google_sql_database_instance" "db0" {
  name             = "db0"
  database_version = "POSTGRES_15"
  region           = var.region
  
  depends_on = [google_project_service.cloud_sql_api]

  settings {
    tier = var.db_tier
    
    disk_size = var.db_disk_size
    disk_type = var.db_disk_type
    
    location_preference {
      zone = var.zone
    }
    
    # Private IP only - access via Cloud SQL Proxy or IAP
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc_network.self_link
    }
    
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

  deletion_protection = true
}

# Databases
# Note: 'postgres' database is created automatically by CloudSQL
resource "google_sql_database" "bh_opie" {
  name     = "bh_opie"
  instance = google_sql_database_instance.db0.name
}

resource "google_sql_database" "bh_opie_test" {
  name     = "bh_opie_test"
  instance = google_sql_database_instance.db0.name
}

# VM Instance with private IP only
resource "google_compute_instance" "opie_stack_vm" {
  name         = "opie-stack-vm"
  machine_type = var.vm_machine_type
  zone         = var.zone
  
  depends_on = [google_project_service.compute_engine_api]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.vm_disk_size
      type  = "pd-ssd"  # SSD for better performance
    }
  }

  labels = merge(var.common_labels, {
    name = "opie-stack-vm"
    type = "compute-instance"
  })

  # Private IP only - access via IAP
  network_interface {
    network    = google_compute_network.vpc_network.id
    subnetwork = google_compute_subnetwork.private_subnet.id
    # No access_config = no public IP
  }

  # Enable OS Login for better security
  metadata = {
    enable-oslogin = "TRUE"
  }

  service_account {
    email  = google_service_account.vm_service_account.email
    scopes = ["cloud-platform"]
  }

  tags = ["http-server", "https-server", "iap-ssh"]
}

# Firewall Rules for private network
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "allow-iap-ssh"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP uses specific IP ranges
  source_ranges = [
    "35.235.240.0/20"  # IAP IP range
  ]
  target_tags = ["iap-ssh"]
}

resource "google_compute_firewall" "allow_internal_http" {
  name    = "allow-internal-http"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["10.0.1.0/24"]  # Private subnet only
  target_tags   = ["http-server", "https-server"]
}

resource "google_compute_firewall" "allow_internal_all" {
  name    = "allow-internal-all"
  network = google_compute_network.vpc_network.name

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

  source_ranges = ["10.0.1.0/24"]  # Private subnet only
}

# Secrets
resource "google_secret_manager_secret" "bh_opie_frontend" {
  secret_id = "bh-opie-frontend"
  
  depends_on = [google_project_service.secret_manager_api]
  
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
  
  depends_on = [google_project_service.secret_manager_api]
  
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
  
  depends_on = [google_project_service.secret_manager_api]
  
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
  
  depends_on = [google_project_service.secret_manager_api]
  
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
  
  depends_on = [google_project_service.secret_manager_api]
  
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
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "sql_backup" {
  account_id   = "sql-backup"
  display_name = "Cloud SQL Backup"
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "bh_opie_storage" {
  account_id   = "bh-opie-storage"
  display_name = "Opie AI Cloud Storage Service Account"
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "cloud_storage_backup" {
  account_id   = "cloud-storage-backup"
  display_name = "Cloud Storage Backup Service Account"
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "github_actions_test" {
  account_id   = "github-actions-test"
  display_name = "GitHub Actions Test Service Account"
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "cloud_run_test" {
  account_id   = "cloud-run-test"
  display_name = "Cloud Run Test Service Account"
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "vm_service_account" {
  account_id   = "vm-service-account"
  display_name = "VM Service Account"
  
  depends_on = [google_project_service.iam_api]
}

# IAP IAM binding for SSH access
resource "google_project_iam_member" "iap_tunnel_resource_accessor" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "user:${var.admin_email}"
  
  depends_on = [google_project_service.iap_api]
}

# Cloud SQL IAM binding for database access
resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.vm_service_account.email}"
}
