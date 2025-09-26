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

# CloudSQL Instance
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
    
    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        name  = "all"
        value = "0.0.0.0/0"
      }
    }
    
    backup_configuration {
      enabled = true
    }
    
    user_labels = merge(var.common_labels, {
      name = "db0"
      type = "cloudsql-instance"
    })
  }

  deletion_protection = false
}

# Databases
resource "google_sql_database" "postgres" {
  name     = "postgres"
  instance = google_sql_database_instance.db0.name
}

resource "google_sql_database" "bh_opie" {
  name     = "bh_opie"
  instance = google_sql_database_instance.db0.name
}

resource "google_sql_database" "bh_opie_test" {
  name     = "bh_opie_test"
  instance = google_sql_database_instance.db0.name
}

# VM Instance
resource "google_compute_instance" "opie_stack_vm" {
  name         = "opie-stack-vm"
  machine_type = var.vm_machine_type
  zone         = var.zone
  
  depends_on = [google_project_service.compute_engine_api]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.vm_disk_size
      type  = "pd-standard"
    }
  }

  labels = merge(var.common_labels, {
    name = "opie-stack-vm"
    type = "compute-instance"
  })

  network_interface {
    network = "default"
    access_config {
      // Ephemeral public IP
    }
  }

  tags = ["http-server", "https-server", "ssh-server"]
}

# Firewall Rules
resource "google_compute_firewall" "default_allow_ssh" {
  name    = "default-allow-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ssh-server"]
}

resource "google_compute_firewall" "default_allow_internal" {
  name    = "default-allow-internal"
  network = "default"

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

  source_ranges = ["10.128.0.0/9"]
}

resource "google_compute_firewall" "allow_http" {
  name    = "allow-http"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["http-server"]
}

resource "google_compute_firewall" "allow_https" {
  name    = "allow-https"
  network = "default"

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
