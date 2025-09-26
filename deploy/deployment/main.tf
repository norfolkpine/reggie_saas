terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = "bh-opie"
  region  = "australia-southeast1"
}

# CloudSQL Instance
resource "google_sql_database_instance" "db0" {
  name             = "db0"
  database_version = "POSTGRES_15"
  region           = "australia-southeast1"

  settings {
    tier = "db-f1-micro"
    
    disk_size = 10
    disk_type = "PD_SSD"
    
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
  machine_type = "e2-medium"
  zone         = "australia-southeast1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-standard"
    }
  }

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
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "bh_opie_backend" {
  secret_id = "bh-opie-backend"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "bh_y_provider" {
  secret_id = "bh-y-provider"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "llamaindex_ingester_env" {
  secret_id = "llamaindex-ingester-env"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "nango_github_actions" {
  secret_id = "nango-github-actions"
  
  replication {
    auto {}
  }
}

# Service Accounts
resource "google_service_account" "bh_opie_github_action" {
  account_id   = "bh-opie-github-action"
  display_name = "bh-opie-github-action"
}

resource "google_service_account" "sql_backup" {
  account_id   = "sql-backup"
  display_name = "Cloud SQL Backup"
}

resource "google_service_account" "bh_opie_storage" {
  account_id   = "bh-opie-storage"
  display_name = "Opie AI Cloud Storage Service Account"
}

resource "google_service_account" "cloud_storage_backup" {
  account_id   = "cloud-storage-backup"
  display_name = "Cloud Storage Backup Service Account"
}

resource "google_service_account" "github_actions_test" {
  account_id   = "github-actions-test"
  display_name = "GitHub Actions Test Service Account"
}

resource "google_service_account" "cloud_run_test" {
  account_id   = "cloud-run-test"
  display_name = "Cloud Run Test Service Account"
}

# Outputs
output "vm_external_ip" {
  description = "External IP address of the VM"
  value       = google_compute_instance.opie_stack_vm.network_interface[0].access_config[0].nat_ip
}

output "db_connection_name" {
  description = "CloudSQL connection name"
  value       = google_sql_database_instance.db0.connection_name
}

output "db_public_ip" {
  description = "CloudSQL public IP address"
  value       = google_sql_database_instance.db0.public_ip_address
}