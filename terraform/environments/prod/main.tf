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

resource "google_project_service" "servicenetworking_api" {
  service = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage_api" {
  service = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "kms_api" {
  service = "cloudkms.googleapis.com"
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

# Reserve IP range for CloudSQL private services
resource "google_compute_global_address" "private_ip_address" {
  name          = "private-ip-address"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc_network.id
  
  depends_on = [google_project_service.servicenetworking_api]
}

# Create private connection to Google services
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc_network.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
  
  depends_on = [google_project_service.servicenetworking_api]
}

# CloudSQL Instance with private IP only
resource "google_sql_database_instance" "db0" {
  name             = "db0"
  database_version = "POSTGRES_15"
  region           = var.region
  
  depends_on = [
    google_project_service.cloud_sql_api,
    google_service_networking_connection.private_vpc_connection
  ]

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

resource "google_service_account" "github_actions_production" {
  account_id   = "github-actions-production"
  display_name = "GitHub Actions Production Service Account"
  
  depends_on = [google_project_service.iam_api]
}

resource "google_service_account" "vm_service_account" {
  account_id   = "vm-service-account"
  display_name = "VM Service Account"
  
  depends_on = [google_project_service.iam_api]
}

# KMS Key for encryption
resource "google_kms_key_ring" "storage_key_ring" {
  name     = "storage-key-ring"
  location = var.region
  
  depends_on = [google_project_service.kms_api]
}

resource "google_kms_crypto_key" "storage_key" {
  name     = "storage-key"
  key_ring = google_kms_key_ring.storage_key_ring.id
  
  purpose = "ENCRYPT_DECRYPT"
  
  version_template {
    algorithm = "GOOGLE_SYMMETRIC_ENCRYPTION"
  }
  
  # lifecycle {
  #   prevent_destroy = true
  # }
}

# Access logs bucket
resource "google_storage_bucket" "access_logs_bucket" {
  name          = "${var.project_id}-access-logs"
  location      = var.region
  force_destroy = false
  
  depends_on = [google_project_service.storage_api]
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  # Shorter retention for logs (1 year)
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }
  
  labels = merge(var.common_labels, {
    name = "access-logs"
    type = "storage-bucket"
    purpose = "access-logs"
  })
}

# Storage Buckets
resource "google_storage_bucket" "media_bucket" {
  name          = var.media_bucket_name
  location      = var.region
  force_destroy = false
  
  depends_on = [
    google_project_service.storage_api,
    google_kms_crypto_key_iam_member.cloud_storage_service_account
  ]
  
  # Security and access control
  uniform_bucket_level_access = true
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption at rest with customer-managed keys
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage_key.id
  }
  
  # Retention policy for compliance (7 years for media files)
  retention_policy {
    retention_period = 2555  # 7 years in days
    is_locked        = true
  }
  
  # Lifecycle management - customer-friendly cost optimization
  lifecycle_rule {
    condition {
      age = 90  # 3 months before archiving (aggressive for cost savings)
      matches_storage_class = ["STANDARD"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 365  # 1 year before moving to coldline
      matches_storage_class = ["NEARLINE"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 1095  # 3 years before moving to archive (preserve customer data)
      matches_storage_class = ["COLDLINE"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
  
  # Only delete very old temporary files (not customer data)
  lifecycle_rule {
    condition {
      age = 2555  # 7 years - only delete if explicitly marked as temporary
      matches_storage_class = ["ARCHIVE"]
      matches_prefix = ["temp/", "cache/", "tmp/"]  # Only temporary files
    }
    action {
      type = "Delete"
    }
  }
  
  # Access logging for security monitoring
  logging {
    log_bucket = google_storage_bucket.access_logs_bucket.name
    log_object_prefix = "media-bucket"
  }
  
  # CORS configuration for web access
  cors {
    origin          = ["https://api.opie.sh", "https://app.opie.sh", "https://${var.project_id}.appspot.com", "https://${var.project_id}.web.app"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
  
  # Website configuration for static content
  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }
  
  labels = merge(var.common_labels, {
    name = var.media_bucket_name
    type = "storage-bucket"
    purpose = "media-files"
    compliance = "retention-7y"
  })
}

resource "google_storage_bucket" "static_bucket" {
  name          = var.static_bucket_name
  location      = var.region
  force_destroy = false
  
  depends_on = [
    google_project_service.storage_api,
    google_kms_crypto_key_iam_member.cloud_storage_service_account
  ]
  
  # Security and access control
  uniform_bucket_level_access = true
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption at rest with customer-managed keys
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage_key.id
  }
  
  # No retention policy for static files (Django static files are frequently accessed)
  # No lifecycle rules for static files (keep in Standard storage for fast access)
  
  # Access logging for security monitoring
  logging {
    log_bucket = google_storage_bucket.access_logs_bucket.name
    log_object_prefix = "static-bucket"
  }
  
  # CORS configuration for web access
  cors {
    origin          = ["https://api.opie.sh", "https://app.opie.sh", "https://${var.project_id}.appspot.com", "https://${var.project_id}.web.app"]
    method          = ["GET", "HEAD"]
    response_header = ["*"]
    max_age_seconds = 86400  # 24 hours for static content
  }
  
  # Website configuration for static content
  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }
  
  labels = merge(var.common_labels, {
    name = var.static_bucket_name
    type = "storage-bucket"
    purpose = "static-files"
    compliance = "no-retention"
  })
}

resource "google_storage_bucket" "docs_bucket" {
  name          = var.docs_bucket_name
  location      = var.region
  force_destroy = false
  
  depends_on = [
    google_project_service.storage_api,
    google_kms_crypto_key_iam_member.cloud_storage_service_account
  ]
  
  # Security and access control
  uniform_bucket_level_access = true
  
  # Versioning for data protection
  versioning {
    enabled = true
  }
  
  # Encryption at rest with customer-managed keys
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage_key.id
  }
  
  # Long retention for documents (10 years for compliance)
  retention_policy {
    retention_period = 3650  # 10 years in days
    is_locked        = true
  }
  
  # Lifecycle management for documents - preserve customer documents
  lifecycle_rule {
    condition {
      age = 180  # 6 months before archiving (documents need longer active access)
      matches_storage_class = ["STANDARD"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 730  # 2 years before moving to coldline
      matches_storage_class = ["NEARLINE"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 1825  # 5 years before moving to archive (preserve customer documents)
      matches_storage_class = ["COLDLINE"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
  
  # Only delete very old temporary documents (not customer documents)
  lifecycle_rule {
    condition {
      age = 3650  # 10 years - only delete if explicitly marked as temporary
      matches_storage_class = ["ARCHIVE"]
      matches_prefix = ["temp/", "cache/", "tmp/", "draft/"]  # Only temporary files
    }
    action {
      type = "Delete"
    }
  }
  
  # Access logging for security monitoring
  logging {
    log_bucket = google_storage_bucket.access_logs_bucket.name
    log_object_prefix = "docs-bucket"
  }
  
  # CORS configuration for web access
  cors {
    origin          = ["https://api.opie.sh", "https://app.opie.sh", "https://${var.project_id}.appspot.com", "https://${var.project_id}.web.app"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
  
  labels = merge(var.common_labels, {
    name = var.docs_bucket_name
    type = "storage-bucket"
    purpose = "document-storage"
    compliance = "retention-10y"
  })
}

# IAP IAM binding for SSH access
resource "google_project_iam_member" "iap_tunnel_resource_accessor" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "group:${var.admin_email}"
  
  depends_on = [google_project_service.iap_api]
}

# Cloud SQL IAM binding for database access
resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.vm_service_account.email}"
}

# GitHub Actions IAM bindings for production
resource "google_project_iam_member" "github_actions_compute_admin" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin"
  member  = "serviceAccount:${google_service_account.github_actions_production.email}"
}

resource "google_project_iam_member" "github_actions_iap_tunnel" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "serviceAccount:${google_service_account.github_actions_production.email}"
}

resource "google_project_iam_member" "github_actions_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_actions_production.email}"
}

resource "google_project_iam_member" "github_actions_cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.github_actions_production.email}"
}

# Storage bucket IAM bindings
resource "google_storage_bucket_iam_member" "media_bucket_admin" {
  bucket = google_storage_bucket.media_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.bh_opie_storage.email}"
}

resource "google_storage_bucket_iam_member" "static_bucket_admin" {
  bucket = google_storage_bucket.static_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.bh_opie_storage.email}"
}

resource "google_storage_bucket_iam_member" "docs_bucket_admin" {
  bucket = google_storage_bucket.docs_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.bh_opie_storage.email}"
}

# GitHub Actions storage access
resource "google_storage_bucket_iam_member" "github_actions_media_bucket_admin" {
  bucket = google_storage_bucket.media_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.github_actions_production.email}"
}

resource "google_storage_bucket_iam_member" "github_actions_static_bucket_admin" {
  bucket = google_storage_bucket.static_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.github_actions_production.email}"
}

resource "google_storage_bucket_iam_member" "github_actions_docs_bucket_admin" {
  bucket = google_storage_bucket.docs_bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.github_actions_production.email}"
}

# VM service account storage access
resource "google_storage_bucket_iam_member" "vm_media_bucket_object_admin" {
  bucket = google_storage_bucket.media_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm_service_account.email}"
}

resource "google_storage_bucket_iam_member" "vm_static_bucket_object_admin" {
  bucket = google_storage_bucket.static_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm_service_account.email}"
}

resource "google_storage_bucket_iam_member" "vm_docs_bucket_object_admin" {
  bucket = google_storage_bucket.docs_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm_service_account.email}"
}

# KMS IAM bindings for encryption key access
resource "google_kms_crypto_key_iam_member" "storage_key_encrypt_decrypt" {
  crypto_key_id = google_kms_crypto_key.storage_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.bh_opie_storage.email}"
}

resource "google_kms_crypto_key_iam_member" "github_actions_storage_key_encrypt_decrypt" {
  crypto_key_id = google_kms_crypto_key.storage_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.github_actions_production.email}"
}

resource "google_kms_crypto_key_iam_member" "vm_storage_key_encrypt_decrypt" {
  crypto_key_id = google_kms_crypto_key.storage_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.vm_service_account.email}"
}

# Cloud Storage service account needs KMS access for bucket encryption
resource "google_kms_crypto_key_iam_member" "cloud_storage_service_account" {
  crypto_key_id = google_kms_crypto_key.storage_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.current.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# Get current project number for Cloud Storage service account
data "google_project" "current" {
  project_id = var.project_id
}
