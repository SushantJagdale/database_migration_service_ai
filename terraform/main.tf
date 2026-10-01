terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {
  project_id = var.project_id
}


# --- APIs to enable ---

resource "google_project_service" "iam" {
  project            = var.project_id
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# Override Org Policy constraint to allow public Cloud Run invocation (if enabled)
resource "google_project_organization_policy" "allow_all_domains" {
  count      = var.override_org_domain_restriction ? 1 : 0
  project    = var.project_id
  constraint = "constraints/iam.allowedPolicyMemberDomains"

  list_policy {
    allow {
      all = true
    }
  }
}


# --- Service Accounts ---

resource "google_service_account" "backend" {
  account_id   = "dms-backend-sa"
  display_name = "Database Migration Service Backend Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.iam]
}

resource "google_service_account" "frontend" {
  account_id   = "dms-frontend-sa"
  display_name = "Database Migration Service Frontend Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.iam]
}

# --- Secret Manager ---

data "google_secret_manager_secret" "google_api_key" {
  secret_id = var.google_api_key_secret_name
  project   = var.project_id
}

# Fetch the latest image digests natively from Artifact Registry (GCR backup repository)
data "google_artifact_registry_docker_image" "backend" {
  location      = "us"
  repository_id = "gcr.io"
  image_name    = "dms-backend:latest"
}

data "google_artifact_registry_docker_image" "frontend" {
  location      = "us"
  repository_id = "gcr.io"
  image_name    = "dms-frontend:latest"
}

# Grant the backend service account access to read secrets in Secret Manager at the Project Level
# This allows the backend to access dynamically created database credential secrets.
resource "google_project_iam_member" "backend_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# Grant the backend service account access to manage Database Migration Service
resource "google_project_iam_member" "backend_dms_admin" {
  project = var.project_id
  role    = "roles/datamigration.admin"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# Grant the backend service account access to manage Cloud SQL instances (for target provisioning)
resource "google_project_iam_member" "backend_cloudsql_admin" {
  project = var.project_id
  role    = "roles/cloudsql.admin"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# Grant the backend service account access to view compute networks and target VPN gateways
resource "google_project_iam_member" "backend_compute_viewer" {
  project = var.project_id
  role    = "roles/compute.networkViewer"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# Grant the backend service account access to read Cloud Logging entries for DMS error diagnosis
resource "google_project_iam_member" "backend_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# --- Cloud Run: Backend Service ---

resource "google_cloud_run_v2_service" "backend" {
  name     = "dms-backend"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"


  template {
    service_account = google_service_account.backend.email

    vpc_access {
      network_interfaces {
        network    = var.vpc_network
        subnetwork = var.vpc_subnetwork
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "gcr.io/${var.project_id}/dms-backend@${split("@", data.google_artifact_registry_docker_image.backend.name)[1]}"
      ports {
        container_port = 8080
      }
      env {
        name  = "MODEL"
        value = var.model_name
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "AWS_ACCESS_KEY_ID"
        value = "none"
      }
      env {
        name  = "AWS_SECRET_ACCESS_KEY"
        value = "none"
      }
      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.google_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  # Ensure IAM bindings are created before service deployment
  depends_on = [
    google_project_service.run,
    google_project_iam_member.backend_secret_accessor,
    google_project_iam_member.backend_dms_admin,
    google_project_iam_member.backend_cloudsql_admin,
    google_project_iam_member.backend_compute_viewer,
    google_project_iam_member.backend_logging_viewer
  ]
}

# Allow unauthenticated (public) access to Backend Service
resource "google_cloud_run_v2_service_iam_member" "backend_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"

  depends_on = [
    google_project_organization_policy.allow_all_domains
  ]
}

# --- Cloud Run: Frontend Service ---

resource "google_cloud_run_v2_service" "frontend" {
  name     = "dms-frontend"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.frontend.email

    containers {
      image = "gcr.io/${var.project_id}/dms-frontend@${split("@", data.google_artifact_registry_docker_image.frontend.name)[1]}"
      ports {
        container_port = 8080
      }
      env {
        name  = "BACKEND_URL"
        value = "https://${google_cloud_run_v2_service.backend.name}-${data.google_project.project.number}.${var.region}.run.app"
      }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_cloud_run_v2_service.backend
  ]
}

# Allow unauthenticated (public) access to Frontend Service
resource "google_cloud_run_v2_service_iam_member" "frontend_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = google_cloud_run_v2_service.frontend.project
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"

  depends_on = [
    google_project_organization_policy.allow_all_domains
  ]
}
